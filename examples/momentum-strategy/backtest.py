"""Synthetic momentum backtest for the FRP demo.

ALL DATA IN THIS EXAMPLE IS SYNTHETIC AND RANDOMLY GENERATED. It is NOT real
market data and must not be used for any real trading or research decision.

The script:
  * generates a deterministic synthetic price series (seeded RNG),
  * runs a simple cross-sectional momentum strategy,
  * computes Sharpe, CAGR, and max drawdown,
  * writes ``metrics.json`` and ``results.csv`` for FRP to capture.

Parameters are read from ``params.json`` if present.
"""

from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).parent
TRADING_DAYS = 252


def load_params() -> dict:
    params_file = HERE / "params.json"
    defaults = {"lookback": 90, "n_assets": 20, "seed": 42, "rebalance": "monthly"}
    if params_file.is_file():
        defaults.update(json.loads(params_file.read_text(encoding="utf-8")))
    return defaults


def generate_prices(n_assets: int, days: int, seed: int) -> list[list[float]]:
    """Generate synthetic geometric-random-walk prices. SYNTHETIC DATA ONLY."""
    rng = random.Random(seed)
    prices = [[100.0 for _ in range(n_assets)]]
    for _ in range(days):
        prev = prices[-1]
        row = []
        for p in prev:
            daily_ret = rng.gauss(0.0003, 0.02)
            row.append(max(0.01, p * math.exp(daily_ret)))
        prices.append(row)
    return prices


def daily_returns(prices: list[list[float]]) -> list[list[float]]:
    rets = []
    for t in range(1, len(prices)):
        rets.append(
            [
                (prices[t][i] / prices[t - 1][i]) - 1.0
                for i in range(len(prices[t]))
            ]
        )
    return rets


def run_strategy(prices: list[list[float]], lookback: int) -> list[float]:
    """Long the top-half momentum assets, short the bottom half, equal weight."""
    rets = daily_returns(prices)
    n_assets = len(prices[0])
    portfolio_returns: list[float] = []

    for t in range(lookback, len(rets)):
        momentum = [
            (prices[t][i] / prices[t - lookback][i]) - 1.0 for i in range(n_assets)
        ]
        ranked = sorted(range(n_assets), key=lambda i: momentum[i])
        half = n_assets // 2
        shorts = set(ranked[:half])
        longs = set(ranked[-half:])
        day_ret = 0.0
        weight = 1.0 / max(1, half)
        for i in range(n_assets):
            if i in longs:
                day_ret += weight * rets[t][i]
            elif i in shorts:
                day_ret -= weight * rets[t][i]
        portfolio_returns.append(day_ret)

    return portfolio_returns


def sharpe(returns: list[float]) -> float:
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(TRADING_DAYS)


def cagr(returns: list[float]) -> float:
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= 1.0 + r
    years = len(returns) / TRADING_DAYS
    if years <= 0 or total <= 0:
        return 0.0
    return total ** (1.0 / years) - 1.0


def max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        dd = (equity / peak) - 1.0
        max_dd = min(max_dd, dd)
    return max_dd


def main() -> None:
    params = load_params()
    lookback = int(params["lookback"])
    n_assets = int(params["n_assets"])
    seed = int(params["seed"])

    prices = generate_prices(n_assets, TRADING_DAYS * 3, seed)
    returns = run_strategy(prices, lookback)

    metrics = {
        "sharpe": round(sharpe(returns), 4),
        "cagr": round(cagr(returns), 4),
        "max_drawdown": round(max_drawdown(returns), 4),
    }

    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    with (HERE / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["day", "portfolio_return"])
        for i, r in enumerate(returns):
            writer.writerow([i, f"{r:.8f}"])

    print("Synthetic momentum backtest complete (SYNTHETIC DATA ONLY).")
    print(f"  lookback={lookback} n_assets={n_assets} seed={seed}")
    print(f"  Sharpe={metrics['sharpe']} CAGR={metrics['cagr']} "
          f"MaxDD={metrics['max_drawdown']}")


if __name__ == "__main__":
    main()