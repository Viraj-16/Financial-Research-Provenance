# Factor-Model Example (synthetic)

> **All data in this example is SYNTHETIC and generated deterministically from a
> seed. It is not real market data and nothing here is investment advice.**

A toy long/short cross-sectional factor portfolio used to demonstrate FRP's
capture, reproduction, and diff workflow. The backtest uses a small deterministic
RNG (no numpy) so results are byte-for-byte reproducible on any machine.

## Files

- `backtest.py` — deterministic synthetic factor backtest.
- `params.json` — parameters (`n_assets`, `n_periods`, `seed`, `top_quantile`).
- Outputs (generated): `results.csv`, `metrics.json`.

## Run it under FRP

```bash
cd examples/factor-model
frpx init
frpx run python backtest.py
```

You'll get an experiment id and detected metrics (`sharpe`, `cagr`,
`max_drawdown`, `ic`).

## Change something and compare

Edit `params.json` (e.g. set `"top_quantile": 0.1`) and run again:

```bash
frpx run python backtest.py
frpx list
frpx diff <old_exp_id> <new_exp_id>
```

The diff shows the changed parameter and the resulting metric differences.

## Verify reproducibility

```bash
frpx reproduce <exp_id>
```

Because the backtest is seeded and deterministic, an unchanged experiment should
report `✓ REPRODUCED`.