"""Tests for Terminal intraday symbol specs."""

from quant_lab.terminal.intraday_spec import (
    LIVE_INTRADAY_SYMBOLS,
    resolve_intraday_spec,
    supports_live_intraday,
)


def test_live_intraday_symbols_include_trinity() -> None:
    assert "^SPX" in LIVE_INTRADAY_SYMBOLS
    assert "SPY" in LIVE_INTRADAY_SYMBOLS
    assert "QQQ" in LIVE_INTRADAY_SYMBOLS


def test_resolve_spy_spec() -> None:
    spec = resolve_intraday_spec("SPY")
    assert spec is not None
    assert spec.option_root == "SPY"
    assert spec.underlying_kind == "stock"
    assert spec.terminal_symbol == "SPY"


def test_resolve_spx_aliases() -> None:
    spx = resolve_intraday_spec("^SPX")
    assert spx is not None
    assert spx.option_root == "SPXW"
    assert resolve_intraday_spec("SPX") == spx


def test_unknown_symbol_has_no_spec() -> None:
    assert resolve_intraday_spec("AAPL") is None
    assert supports_live_intraday("AAPL") is False
