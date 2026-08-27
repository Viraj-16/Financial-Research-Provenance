"""Synthetic factor-model backtest (SYNTHETIC DATA ONLY).

This is a deterministic, self-contained example for demonstrating FRP. It does
NOT use real market data and its "results" are not investment advice. It builds
a toy cross-sectional value+momentum factor portfolio on random-but-seeded data.

Parameters are read from params.json (or FRP's --param overrides via argv are
NOT consumed here; this script reads its own params.json to stay deterministic).

Outputs:
  * results.csv  — per-period portfolio returns
  * metrics.json — sharpe, cagr, max_drawdown, ic
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_params() -> dict:
    p = ROOT / "params.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"n_assets": 50, "n_periods": 252, "seed": 7, "top_quantile": 0.2}


class LCG:
    """Deterministic linear congruential generator (no numpy dependency)."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def next_float(self) -> float:
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state / 0x7FFFFFFF

    def normal(self) -> float:
        # Box-Muller using two uniforms.
        u1 = max(self.next_float(), 1e-12)
        u2 = self.next_float()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def run() -> None:
    params = load_params()
    n_assets = int(params.get("n_assets", 50))
    n_periods = int(params.get("n_periods", 252))
    seed = int(params.get("seed", 7))
    top_q = float(params.get("top_quantile", 0.2))

    rng = LCG(seed)

    # Latent "factor" score per asset (value+momentum proxy) and a true beta to it.
    scores = [rng.normal() for _ in range(n_assets)]
    betas = [0.3 * s + 0.1 * rng.normal() for s in scores]

    n_top = max(1, int(n_assets * top_q))
    ranked = sorted(range(n_assets), key=lambda i: scores[i], reverse=True)
    longs = set(ranked[:n_top])
    shorts = set(ranked[-n_top:])

    period_returns: list[float] = []
    ics: list[float] = []
    for _ in range(n_periods):
        factor_ret = 0.0004 + 0.01 * rng.normal()  # daily factor return
        asset_rets = [betas[i] * factor_ret + 0.02 * rng.normal() for i in range(n_assets)]
        long_ret = sum(asset_rets[i] for i in longs) / len(longs)
        short_ret = sum(asset_rets[i] for i in shorts) / len(shorts)
        period_returns.append(long_ret - short_ret)

        # Information coefficient proxy: sign agreement between score and return.
        agree = sum(1 for i in range(n_assets) if (scores[i] > 0) == (asset_rets[i] > 0))
        ics.append(2.0 * agree / n_assets - 1.0)

    # Metrics
    mean = sum(period_returns) / len(period_returns)
    var = sum((r - mean) ** 2 for r in period_returns) / max(1, len(period_returns) - 1)
    std = math.sqrt(var)
    sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in period_returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
    years = len(period_returns) / 252.0
    cagr = equity ** (1.0 / years) - 1.0 if years > 0 and equity > 0 else 0.0
    ic = sum(ics) / len(ics)

    # Outputs
    with (ROOT / "results.csv").open("w", encoding="utf-8") as f:
        f.write("period,return\n")
        for i, r in enumerate(period_returns):
            f.write(f"{i},{r:.6f}\n")

    metrics = {
        "sharpe": round(sharpe, 4),
        "cagr": round(cagr, 4),
        "max_drawdown": round(max_dd, 4),
        "ic": round(ic, 4),
    }
    (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("Synthetic factor-model backtest complete (SYNTHETIC DATA ONLY).")
    print(f"  n_assets={n_assets} n_periods={n_periods} seed={seed} top_quantile={top_q}")
    print(
        f"  Sharpe={metrics['sharpe']} CAGR={metrics['cagr']} "
        f"MaxDD={metrics['max_drawdown']} IC={metrics['ic']}"
    )


if __name__ == "__main__":
    run()