# FRP Architecture

FRP is a local-first provenance layer that versions the *entire research state*
of a quantitative experiment. It complements Git (which versions source) by
capturing code + data + environment + parameters + execution + results at run
time as an **immutable** record.

## Components

```
frp/
  cli/          Typer app (frpx) + Rich rendering
  capture/      git, environment/dependencies, parameters
  execution/    subprocess runner, metric detection
  experiments/  id generation + immutable create/query service
  datasets/     fingerprinting + registry (Phase 2)
  reproduction/ re-run + compare (Phase 3)
  diff/         experiment/dataset diff (Phase 4)
  validation/   data quality + point-in-time + look-ahead (Phase 5)
  models/       SQLAlchemy ORM
  store/        paths, config, SQLite engine/session
```

## Storage

Everything lives under `.frp/` at the project root:

- `frp.db` — SQLite metadata + provenance (via SQLAlchemy 2.0).
- `artifacts/<experiment_id>/` — copied output files (immutable).
- `config.toml` — project config.

## Immutability

- Provenance rows are written once by the experiment service; there is no update
  path for them.
- Each experiment stores a `content_hash = sha256(canonical_json(aggregate))`
  and a `frozen_at` timestamp.
- Re-running produces a **new** `exp_...` id. Identical inputs produce an
  identical `content_hash`, which is how reproduction is verified.

## Data identity vs. data storage

FRP always computes dataset **identity** (SHA-256 + schema/rowcount/date-range
metadata). Copying raw bytes into the store (**storage**) is a separate, opt-in
concern. This separation is what allows large datasets to be fingerprinted
without being uploaded.

## Point-in-time foundation

`dataset_snapshot` carries optional `observation_date`, `publication_date`,
`effective_date`, and `revision_ts`. These are populated **only** when a dataset
actually provides them. FRP does not fabricate historical availability.

## Data model (tables)

`project`, `experiment`, `git_commit`, `environment`, `dependency`, `dataset`,
`dataset_snapshot`, `experiment_dataset`, `parameter`, `artifact`, `metric`,
`lineage_edge`, `validation_result`.

Key constraints/indexes: unique `(dataset_id, sha256)`, unique
`(environment_id, name, version)`, index on `dataset_snapshot.sha256`, index on
`experiment(project_id, started_at)` and `metric(experiment_id, key)`.