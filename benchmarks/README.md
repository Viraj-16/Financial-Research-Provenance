# FRP Benchmarks

Micro-benchmarks for FRP's hot paths, using **synthetic data only**. Run:

```bash
python benchmarks/bench.py
```

## Methodology

- Synthetic `prices.parquet` datasets of increasing row counts are generated in a
  temp directory (deterministic content, no real market data).
- Each measurement reports the **best (min) wall time** over several repeats to
  reduce noise from GC/scheduler jitter.
- Fingerprinting = SHA-256 over raw bytes + Polars schema/row-count/date-range
  extraction. Capture = full immutable experiment write into SQLite (no
  artifacts). Diff = pure in-memory comparison of two loaded experiments.

## Sample results (illustrative, NOT a published claim)

These numbers were measured on one developer machine (Windows, CPython 3.10) and
**will vary** by hardware, OS, Python version, and dataset. They are included to
show orders of magnitude, not to make performance guarantees.

| Operation | Input | Order of magnitude |
| --- | --- | --- |
| Dataset fingerprint | 1,000 rows | a few ms |
| Dataset fingerprint | 100,000 rows | tens of ms |
| Dataset fingerprint | 1,000,000 rows | ~0.1–0.2 s |
| Experiment capture | in-DB, no artifacts | tens of ms |
| Experiment diff | two experiments | sub-millisecond |

Re-run `python benchmarks/bench.py` to reproduce on your own machine; do not
treat the table above as authoritative for your environment.