# Momentum Strategy Example (SYNTHETIC DATA)

> **All data in this example is synthetic and randomly generated. It is NOT real
> market data and must not be used for any real trading or research decision.**

A minimal cross-sectional momentum backtest used to demonstrate the FRP
workflow end-to-end.

## Files

- `backtest.py` — generates synthetic prices (seeded), runs the strategy, and
  writes `metrics.json` and `results.csv`.
- `params.json` — strategy parameters captured by FRP.

## Run it with FRP

```bash
cd examples/momentum-strategy
frpx init
frpx run python backtest.py
frpx list
frpx show <experiment_id>
```

## Show what changed

Change a parameter and run again:

```bash
frpx run python backtest.py --param lookback=120
frpx diff <old_experiment_id> <new_experiment_id>   # Phase 4
```

The diff will highlight the parameter change (`lookback: 90 → 120`) and the
resulting metric changes.