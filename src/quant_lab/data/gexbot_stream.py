"""GEXBot WebSocket structure stream + in-memory vendor state (Quant tier)."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import requests
from azure.messaging.webpubsubclient import WebPubSubClient
from azure.messaging.webpubsubclient.models import (
    CallbackType,
    OnConnectedArgs,
    OnDisconnectedArgs,
    OnGroupDataMessageArgs,
)
from google.protobuf import any_pb2

from quant_lab.config import env_var
from quant_lab.data.gexbot_client import (
    DEFAULT_USER_AGENT,
    GEXBOT_BASE_URL,
    GexbotConfigError,
    get_gexbot_client,
    gexbot_ticker,
    resolve_gexbot_api_key,
)
from quant_lab.data.gexbot_ws_decode import decode_gex_message, decode_orderflow_message
from quant_lab.terminal.structure_history import record_structure_sample

log = logging.getLogger(__name__)

ConnectionStatus = Literal["live", "reconnecting", "rest_fallback", "stopped", "disabled"]

DEFAULT_WS_GROUPS = ("SPX_classic_gex_zero", "SPX_orderflow_orderflow")
DEFAULT_STATE_WS_GROUPS = (
    "SPX_state_gamma_zero",
    "SPX_state_vanna_zero",
    "SPX_state_charm_zero",
    "SPX_state_delta_zero",
)
_STALE_SEC_DEFAULT = 15.0
_REST_FALLBACK_SEC_DEFAULT = 60.0

_lock = threading.RLock()
_state_by_ticker: dict[str, VendorStreamState] = {}
_service: GexbotStreamService | None = None


def _env_enabled(name: str, *, default: str = "1") -> bool:
    raw = env_var(name, default=default)
    return raw is not None and raw.strip().lower() not in ("0", "false", "no", "off")


def _env_float(name: str, default: float) -> float:
    raw = env_var(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def gexbot_ws_enabled() -> bool:
    return _env_enabled("TERMINAL_GEXBOT_WS")


def gexbot_ws_state_hubs_enabled() -> bool:
    return _env_enabled("TERMINAL_GEXBOT_WS_STATE", default="0")


def default_ws_groups() -> tuple[str, ...]:
    raw = env_var("TERMINAL_GEXBOT_WS_GROUPS")
    if raw is not None and raw.strip():
        return tuple(g.strip() for g in raw.split(",") if g.strip())
    groups = list(DEFAULT_WS_GROUPS)
    if gexbot_ws_state_hubs_enabled():
        groups.extend(DEFAULT_STATE_WS_GROUPS)
    return tuple(groups)


def _state_hub_key_from_group(group: str) -> str | None:
    """``SPX_state_vanna_zero`` → ``vanna_zero``."""
    if "_state_" not in group:
        return None
    suffix = group.split("_state_", 1)[1]
    return suffix if suffix else None


def _hub_for_group(group: str) -> str:
    if "_classic_" in group:
        return "classic"
    if "_orderflow_" in group:
        return "orderflow"
    if "_state_" in group:
        suffix = group.split("_state_", 1)[1]
        family = suffix.split("_")[0] if suffix else "gex"
        return f"state_{family}"
    return "classic"


def _ticker_from_group(group: str) -> str:
    # e.g. SPX_classic_gex_zero → SPX; ES_SPX_classic_gex_zero → ES_SPX
    for sep in ("_classic_", "_orderflow_", "_state_"):
        if sep in group:
            return group.split(sep)[0]
    return group.split("_")[0]


@dataclass
class VendorStreamState:
    ticker: str
    updated_at: datetime | None = None
    spot: float | None = None
    classic: dict[str, Any] = field(default_factory=dict)
    orderflow: dict[str, Any] = field(default_factory=dict)
    state_hubs: dict[str, dict[str, Any]] = field(default_factory=dict)
    connection_status: ConnectionStatus = "stopped"
    last_ws_at: float | None = None
    last_rest_at: float | None = None
    hubs: list[str] = field(default_factory=list)

    def age_seconds(self) -> float | None:
        if self.last_ws_at is None and self.last_rest_at is None:
            return None
        ref = self.last_ws_at or self.last_rest_at
        return time.monotonic() - ref if ref is not None else None

    def is_fresh(self, *, max_age: float) -> bool:
        age = self.age_seconds()
        return age is not None and age <= max_age

    def to_meta(self) -> dict[str, Any]:
        updated_ms: int | None = None
        if self.updated_at is not None:
            updated_ms = int(self.updated_at.timestamp() * 1000)
        source = "gexbot_ws"
        if self.connection_status == "rest_fallback":
            source = "gexbot_rest"
        elif self.connection_status in ("stopped", "disabled"):
            source = "stale"
        return {
            "source": source,
            "connection_status": self.connection_status,
            "last_update_ms": updated_ms,
            "hubs": list(self.hubs),
            "ticker": self.ticker,
        }


def get_vendor_stream_state(terminal_symbol: str) -> VendorStreamState | None:
    ticker = gexbot_ticker(terminal_symbol)
    with _lock:
        return _state_by_ticker.get(ticker)


def _terminal_symbol_from_ticker(ticker: str) -> str:
    return f"^{ticker}" if ticker.upper() == "SPX" else ticker


def get_vendor_payloads(
    terminal_symbol: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Classic + orderflow + optional state hub payloads for structure / fusion."""
    classic = get_vendor_classic_payload(terminal_symbol)
    stream = get_vendor_stream_state(terminal_symbol)
    orderflow = dict(stream.orderflow) if stream is not None and stream.orderflow else None
    state_hubs = (
        {k: dict(v) for k, v in stream.state_hubs.items()}
        if stream is not None and stream.state_hubs
        else {}
    )
    return classic, orderflow, state_hubs


def get_vendor_classic_payload(terminal_symbol: str) -> dict[str, Any] | None:
    """Classic GEX payload for overlay — WS state first, REST fallback if stale."""
    if not gexbot_ws_enabled():
        return _fetch_classic_rest(terminal_symbol)

    stale_sec = _env_float("TERMINAL_GEXBOT_WS_STALE_SEC", _STALE_SEC_DEFAULT)
    state = get_vendor_stream_state(terminal_symbol)
    if state is not None and state.classic and state.is_fresh(max_age=stale_sec):
        return dict(state.classic)

    if state is not None and state.classic:
        # WS connected but slightly stale — still serve cache, trigger async REST backfill
        _schedule_rest_backfill(terminal_symbol)
        return dict(state.classic)

    return _fetch_classic_rest(terminal_symbol)


def vendor_overlay_from_stream_or_rest(terminal_symbol: str) -> dict[str, Any] | None:
    """Levels + pin ladder for snapshot meta."""
    from quant_lab.data.vendor_chain import (
        vendor_levels_from_classic,
        vendor_pin_ladder_from_classic,
    )

    classic = get_vendor_classic_payload(terminal_symbol)
    if classic is None:
        return None
    levels = vendor_levels_from_classic(classic)
    levels["source"] = "gexbot"
    levels["gex_method"] = "vendor_precomputed"
    stream = get_vendor_stream_state(terminal_symbol)
    if stream is not None:
        levels["stream"] = stream.to_meta()
        if stream.orderflow:
            levels["gex_orderflow"] = stream.orderflow.get("gex_orderflow")
    ladder = vendor_pin_ladder_from_classic(classic)
    return {
        "levels": levels,
        "pin_ladder": ladder,
        "max_priors_raw": classic.get("max_priors") or [],
    }


def _schedule_rest_backfill(terminal_symbol: str) -> None:
    svc = _service
    if svc is not None:
        svc.request_rest_backfill(terminal_symbol)


def _fetch_classic_rest(terminal_symbol: str) -> dict[str, Any] | None:
    try:
        client = get_gexbot_client()
        ticker = gexbot_ticker(terminal_symbol)
        payload = client.classic(ticker, "gex_zero")
        with _lock:
            state = _state_by_ticker.setdefault(ticker, VendorStreamState(ticker=ticker))
            state.classic = payload
            state.spot = float(payload.get("spot", 0)) if payload.get("spot") is not None else None
            state.updated_at = datetime.now(UTC)
            state.last_rest_at = time.monotonic()
            state.connection_status = "rest_fallback"
        return payload
    except (GexbotConfigError, OSError, ValueError) as exc:
        log.debug("GEXBot REST classic fallback failed: %s", exc)
        return None


class _HubClient:
    def __init__(
        self,
        hub_key: str,
        connection_url: str,
        groups: list[str],
        on_message: Any,
    ) -> None:
        self.hub_key = hub_key
        self.groups = groups
        self._on_message = on_message
        self._client = WebPubSubClient(connection_url)
        self._thread: threading.Thread | None = None
        self._client.subscribe(CallbackType.CONNECTED, self._on_connected)
        self._client.subscribe(CallbackType.DISCONNECTED, self._on_disconnected)
        self._client.subscribe(CallbackType.GROUP_MESSAGE, self._on_group_message)

    def _run_client(self) -> None:
        try:
            self._client.open()
        except Exception as exc:
            log.warning("GEXBot WS hub %s connection failed: %s", self.hub_key, exc)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run_client,
            name=f"gexbot-ws-{self.hub_key}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        with contextlib.suppress(OSError):
            self._client.close()

    def _on_connected(self, event: OnConnectedArgs) -> None:
        log.info("GEXBot WS hub %s connected (%s)", self.hub_key, event.connection_id)

    def _on_disconnected(self, event: OnDisconnectedArgs) -> None:
        log.warning("GEXBot WS hub %s disconnected: %s", self.hub_key, event.message)

    def _on_group_message(self, event: OnGroupDataMessageArgs) -> None:
        try:
            any_message = any_pb2.Any()
            any_message.ParseFromString(event.data)
            self._on_message(self.hub_key, event.group, any_message)
        except Exception as exc:
            log.debug("GEXBot WS parse error on %s: %s", self.hub_key, exc)


class GexbotStreamService:
    """Background GEXBot WebSocket subscriber (one process-wide instance)."""

    def __init__(
        self,
        *,
        api_key: str,
        groups: tuple[str, ...] | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        base_url: str = GEXBOT_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._groups = groups or default_ws_groups()
        self._user_agent = user_agent
        self._negotiate_url = f"{base_url.rstrip('/')}/negotiate"
        self._shutdown = threading.Event()
        self._hub_clients: list[_HubClient] = []
        self._watchdog: threading.Thread | None = None
        self._backfill_lock = threading.Lock()
        self._last_backfill: dict[str, float] = {}

    def start(self) -> None:
        if self._watchdog is not None:
            return
        try:
            self._connect()
        except Exception as exc:
            log.warning("GEXBot WS negotiate failed — REST fallback only: %s", exc)
        self._watchdog = threading.Thread(target=self._run_watchdog, name="gexbot-ws-watchdog", daemon=True)
        self._watchdog.start()
        log.info("GEXBot stream service started (%d groups)", len(self._groups))

    def stop(self) -> None:
        self._shutdown.set()
        for client in self._hub_clients:
            client.stop()
        self._hub_clients.clear()
        if self._watchdog is not None:
            self._watchdog.join(timeout=3.0)
            self._watchdog = None
        with _lock:
            for state in _state_by_ticker.values():
                state.connection_status = "stopped"

    def request_rest_backfill(self, terminal_symbol: str) -> None:
        ticker = gexbot_ticker(terminal_symbol)
        now = time.monotonic()
        with self._backfill_lock:
            if now - self._last_backfill.get(ticker, 0.0) < 10.0:
                return
            self._last_backfill[ticker] = now
        threading.Thread(
            target=_fetch_classic_rest,
            args=(terminal_symbol,),
            name=f"gexbot-rest-{ticker}",
            daemon=True,
        ).start()

    def _negotiate(self) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            self._negotiate_url,
            headers=headers,
            json={"groups": list(self._groups)},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("negotiate response must be object")
        return payload

    def _connect(self) -> None:
        data = self._negotiate()
        urls = data.get("websocket_urls")
        if not isinstance(urls, dict):
            raise ValueError("negotiate missing websocket_urls")

        hub_groups: dict[str, list[str]] = {}
        for group in self._groups:
            hub = _hub_for_group(group)
            hub_groups.setdefault(hub, []).append(group)
            ticker = _ticker_from_group(group)
            with _lock:
                _state_by_ticker.setdefault(ticker, VendorStreamState(ticker=ticker))

        for hub_key, url in urls.items():
            groups = hub_groups.get(hub_key, [])
            if not groups:
                continue
            if not isinstance(url, str) or not url:
                continue
            client = _HubClient(hub_key, url, groups, self._handle_message)
            client.start()
            self._hub_clients.append(client)
            with _lock:
                for g in groups:
                    t = _ticker_from_group(g)
                    st = _state_by_ticker.setdefault(t, VendorStreamState(ticker=t))
                    st.connection_status = "live"
                    if hub_key not in st.hubs:
                        st.hubs.append(hub_key)

    def _handle_message(self, hub_key: str, group: str, any_message: any_pb2.Any) -> None:
        type_url = any_message.type_url
        ticker = _ticker_from_group(group)
        now_mono = time.monotonic()
        now_utc = datetime.now(UTC)

        if "proto.gex" in type_url:
            payload = decode_gex_message(any_message)
            state_key = _state_hub_key_from_group(group)
            terminal_symbol = _terminal_symbol_from_ticker(ticker)
            with _lock:
                state = _state_by_ticker.setdefault(ticker, VendorStreamState(ticker=ticker))
                spot = payload.get("spot")
                if spot is not None:
                    state.spot = float(spot)
                state.updated_at = now_utc
                state.last_ws_at = now_mono
                state.connection_status = "live"
                if state_key is not None:
                    state.state_hubs[state_key] = payload
                    classic_snapshot = dict(state.classic) if state.classic else None
                    orderflow_snapshot = dict(state.orderflow) if state.orderflow else None
                    spot_snapshot = state.spot
                else:
                    state.classic = payload
                    orderflow_snapshot = dict(state.orderflow) if state.orderflow else None
                    spot_snapshot = state.spot
                    classic_snapshot = payload
            if state_key is None:
                record_structure_sample(
                    terminal_symbol,
                    classic=classic_snapshot,
                    orderflow=orderflow_snapshot,
                    spot=spot_snapshot,
                )
            return

        if "proto.orderflow" in type_url:
            orderflow = decode_orderflow_message(any_message)
            terminal_symbol = _terminal_symbol_from_ticker(ticker)
            with _lock:
                state = _state_by_ticker.setdefault(ticker, VendorStreamState(ticker=ticker))
                state.orderflow = orderflow
                spot = orderflow.get("spot")
                if spot is not None:
                    state.spot = float(spot)
                state.updated_at = now_utc
                state.last_ws_at = now_mono
                state.connection_status = "live"
                classic_snapshot = dict(state.classic) if state.classic else None
                spot_snapshot = state.spot
            record_structure_sample(
                terminal_symbol,
                classic=classic_snapshot,
                orderflow=orderflow,
                spot=spot_snapshot,
            )

    def _run_watchdog(self) -> None:
        stale_sec = _env_float("TERMINAL_GEXBOT_WS_STALE_SEC", _STALE_SEC_DEFAULT)
        fallback_sec = _env_float("TERMINAL_GEXBOT_WS_FALLBACK_SEC", _REST_FALLBACK_SEC_DEFAULT)
        while not self._shutdown.wait(timeout=5.0):
            with _lock:
                tickers = list(_state_by_ticker.keys())
            for ticker in tickers:
                with _lock:
                    state = _state_by_ticker.get(ticker)
                if state is None:
                    continue
                age = state.age_seconds()
                if age is None:
                    continue
                if age > fallback_sec and not self._hub_clients:
                    state.connection_status = "rest_fallback"
                    self.request_rest_backfill(f"^{ticker}" if ticker == "SPX" else ticker)
                elif age > stale_sec:
                    state.connection_status = "reconnecting"
                    self.request_rest_backfill(f"^{ticker}" if ticker == "SPX" else ticker)


def start_gexbot_stream_service() -> None:
    """Start process-wide stream (no-op when disabled or no API key)."""
    global _service
    if _service is not None:
        return
    if not gexbot_ws_enabled():
        log.info("GEXBot WebSocket disabled (TERMINAL_GEXBOT_WS=0)")
        return
    key = resolve_gexbot_api_key()
    if key is None:
        log.warning("GEXBot WebSocket skipped — no API key")
        return
    _service = GexbotStreamService(api_key=key)
    _service.start()


def stop_gexbot_stream_service() -> None:
    global _service
    if _service is not None:
        _service.stop()
        _service = None


def stream_status() -> dict[str, Any]:
    """Health payload fragment."""
    with _lock:
        tickers = {
            t: {
                "connection_status": s.connection_status,
                "age_seconds": s.age_seconds(),
                "spot": s.spot,
                "hubs": s.hubs,
            }
            for t, s in _state_by_ticker.items()
        }
    return {
        "ws_enabled": gexbot_ws_enabled(),
        "ws_groups": list(default_ws_groups()),
        "tickers": tickers,
    }
