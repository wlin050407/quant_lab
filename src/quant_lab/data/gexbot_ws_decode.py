"""Decode GEXBot WebSocket zstd+protobuf payloads (NFA quant-python-sockets semantics)."""

from __future__ import annotations

from typing import Any

import zstandard
from google.protobuf import any_pb2

from quant_lab.data.gexbot_proto import gex_pb2, orderflow_pb2

_DCTX = zstandard.ZstdDecompressor()


def _decompress_any_bytes(any_message: any_pb2.Any) -> bytes:
    with _DCTX.stream_reader(any_message.value) as reader:
        return reader.read()


def decode_gex_message(any_message: any_pb2.Any) -> dict[str, Any]:
    """Decode classic/state GEX protobuf wrapped in ``google.protobuf.Any``."""
    decompressed = _decompress_any_bytes(any_message)
    decoded = gex_pb2.Gex()
    decoded.ParseFromString(decompressed)
    return {
        "timestamp": decoded.timestamp,
        "ticker": decoded.ticker,
        "min_dte": decoded.min_dte or 0,
        "sec_min_dte": decoded.sec_min_dte or 1,
        "spot": (decoded.spot or 0) / 100.0,
        "zero_gamma": (decoded.zero_gamma or 0) / 100.0,
        "major_pos_vol": (decoded.major_pos_vol or 0) / 100.0,
        "major_pos_oi": (decoded.major_pos_oi or 0) / 100.0,
        "major_neg_vol": (decoded.major_neg_vol or 0) / 100.0,
        "major_neg_oi": (decoded.major_neg_oi or 0) / 100.0,
        "strikes": [
            [
                (s.strike_price or 0) / 100.0,
                (s.value_1 or 0) / 100.0,
                (s.value_2 or 0) / 100.0,
                [v / 100.0 for v in s.priors.values] if s.HasField("priors") else [],
            ]
            for s in decoded.strikes
        ],
        "sum_gex_vol": (decoded.sum_gex_vol or 0) / 1000.0,
        "sum_gex_oi": (decoded.sum_gex_oi or 0) / 1000.0,
        "delta_risk_reversal": (decoded.delta_risk_reversal or 0) / 1000.0,
        "max_priors": [
            [(t.first_value or 0) / 100.0, (t.second_value or 0) / 1000.0]
            for t in decoded.max_priors.tuples
        ]
        if decoded.HasField("max_priors")
        else [],
    }


def decode_orderflow_message(any_message: any_pb2.Any) -> dict[str, Any]:
    """Decode orderflow hub protobuf."""
    decompressed = _decompress_any_bytes(any_message)
    p = orderflow_pb2.Orderflow()
    p.ParseFromString(decompressed)
    return {
        "timestamp": p.timestamp,
        "ticker": p.ticker,
        "spot": (p.spot or 0) / 100.0,
        "zero_gex_ratio": p.zero_gex_ratio / 100.0,
        "one_gex_ratio": p.one_gex_ratio / 100.0,
        "gex_orderflow": p.gex_orderflow / 100.0,
        "one_gex_orderflow": p.one_gex_orderflow / 100.0,
        "dex_orderflow": p.dex_orderflow / 100.0,
        "zero_net_total_dex": p.zero_net_total_dex / 100.0,
    }
