"""Baseline Z-score mean-reversion backtest CLI."""

from __future__ import annotations

import argparse
import logging
import sys

from quant_lab.backtest.engine import run_backtest
from quant_lab.data.storage import load_underlying
from quant_lab.strategies.baseline_zscore import zscore_mean_reversion_signals

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--scale-z", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--commission-bps", type=float, default=0.0)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    try:
        bars = load_underlying(args.symbol, interval="1d")
    except FileNotFoundError as exc:
        print(f"underlying missing: {exc}", file=sys.stderr)
        return 1

    close = bars["close"].astype("float64")
    signals = zscore_mean_reversion_signals(close, window=args.window, scale_z=args.scale_z)
    result = run_backtest(
        close,
        signals,
        slippage_bps=args.slippage_bps,
        commission_bps=args.commission_bps,
    )

    print(f"=== baseline Z-score backtest: {args.symbol} ===")
    print(f"window={args.window}  scale_z={args.scale_z}")
    print(f"days:         {result.stats.n_days}")
    print(f"total return: {result.stats.total_return:+.2%}")
    print(f"Sharpe:       {result.stats.sharpe:.2f}")
    print(f"max drawdown: {result.stats.max_drawdown:.2%}")
    print(f"hit rate:     {result.stats.hit_rate:.2%}")
    print(f"turnover:     {result.stats.turnover:.2f} (sum |Δweight|)")
    print(f"final equity: {result.equity_curve.iloc[-1]:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
