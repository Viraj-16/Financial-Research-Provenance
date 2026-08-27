# FRP Security Model

FRP is a **local-first developer tool**. This document states plainly what FRP
does and does not protect against.

## Code execution is local and NOT sandboxed

`frpx run <command>` executes the command **in your own shell context, with your
own user permissions**. FRP does not sandbox, containerize, or otherwise isolate
the code it runs. **Only run code you trust.** This is equivalent to running the
command yourself in a terminal.

We deliberately do **not** claim local execution is safe or isolated.

## No remote code execution

FRP never fetches or executes code received over a network. There is no
server-side arbitrary-code-execution service in this MVP.

## Defensive measures that ARE implemented

- **Experiment id validation.** Experiment ids are validated against a strict
  `^exp_[0-9a-f]{12}$` pattern *before* any database lookup. Malformed input
  (including SQL-injection-style strings and path-traversal strings) is rejected.
- **Artifact path containment.** Output artifacts are recorded only if they
  resolve to a path *inside* the project root. Files that would escape the
  project root (e.g. via `..`) are refused.
- **No `eval` / no dynamic import of untrusted data.** Metadata files
  (`params.json`, `metrics.json`) are parsed as JSON with the standard library;
  invalid JSON raises a clear error rather than executing anything.
- **Read-only dashboard (planned).** The web dashboard reads the local SQLite
  database and does not execute research code.

## If server-side execution is added later

It must, at minimum:

- isolate jobs (containers / VMs),
- restrict network access,
- restrict filesystem access,
- impose CPU/memory limits,
- run as a non-root user,
- enforce timeouts.

None of the above is implemented in the local MVP because the MVP does not run
untrusted or remote code.