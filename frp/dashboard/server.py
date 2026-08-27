"""Static, read-only dashboard renderer and local server.

The dashboard is a single self-contained HTML page with the store data embedded
as JSON. It reads nothing at runtime beyond that snapshot and executes no
research code. Served locally via the Python stdlib ``http.server``.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>FRP Dashboard — __PROJECT__</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         margin: 0; background: #0b0e14; color: #e6e6e6; }}
  header {{ padding: 20px 28px; border-bottom: 1px solid #222; background: #11151f; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header .sub {{ color: #8a94a6; font-size: 13px; margin-top: 4px; }}
  main {{ padding: 24px 28px; max-width: 1100px; margin: 0 auto; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #151a26; border: 1px solid #232a3a; border-radius: 10px; padding: 14px 16px; }}
  .card .k {{ color: #8a94a6; font-size: 12px; }}
  .card .v {{ font-size: 20px; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #222b3a; }}
  th {{ color: #8a94a6; font-weight: 600; }}
  tr.exp {{ cursor: pointer; }}
  tr.exp:hover {{ background: #151a26; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #9ecbff; }}
  .status-completed {{ color: #5ad67d; }}
  .status-failed {{ color: #ff6b6b; }}
  .detail {{ background: #0f131c; border: 1px solid #232a3a; border-radius: 10px;
             padding: 16px 18px; margin-top: 8px; }}
  .detail h3 {{ margin: 14px 0 6px; font-size: 13px; color: #8a94a6;
                text-transform: uppercase; letter-spacing: .04em; }}
  .kv {{ display: grid; grid-template-columns: 160px 1fr; gap: 4px 12px; font-size: 13px; }}
  .muted {{ color: #6b7488; }}
  .hidden {{ display: none; }}
  a {{ color: #9ecbff; }}
</style>
</head>
<body>
<header>
  <h1>Financial Research Provenance</h1>
  <div class="sub">Project <code>__PROJECT__</code> · read-only dashboard · all data local</div>
</header>
<main>
  <div class="cards" id="cards"></div>
  <h2 style="font-size:15px;color:#8a94a6;">Experiments</h2>
  <table>
    <thead><tr><th>ID</th><th>Started</th><th>Commit</th><th>Status</th><th>Key metrics</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="detail"></div>
</main>
<script id="frp-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("frp-data").textContent);
const fmt = (v) => (v === null || v === undefined) ? "-" : v;
const shortHash = (h) => h ? h.slice(0, 8) : "-";

function renderCards() {{
  const p = DATA.project;
  document.getElementById("cards").innerHTML = [
    ["Experiments", p.experiment_count],
    ["Latest", p.latest_experiment ? p.latest_experiment : "-"],
    ["Last activity", p.last_activity ? new Date(p.last_activity).toLocaleString() : "-"],
  ].map(([k, v]) => `<div class="card"><div class="k">${{k}}</div><div class="v">${{v}}</div></div>`).join("");
}}

function metricsSummary(m) {{
  const keys = Object.keys(m).sort().slice(0, 3);
  return keys.length ? keys.map(k => `${{k}}=${{m[k]}}`).join(", ") : "-";
}}

function renderRows() {{
  const rows = DATA.experiments.map((e) => `
    <tr class="exp" data-id="${{e.id}}">
      <td><code>${{e.id}}</code></td>
      <td>${{e.started_at ? new Date(e.started_at).toLocaleString() : "-"}}</td>
      <td><code>${{shortHash(e.git_commit)}}</code></td>
      <td class="status-${{e.status}}">${{e.status}}</td>
      <td>${{metricsSummary(e.metrics)}}</td>
    </tr>`).join("");
  document.getElementById("rows").innerHTML = rows ||
    `<tr><td colspan="5" class="muted">No experiments yet.</td></tr>`;
  document.querySelectorAll("tr.exp").forEach((tr) =>
    tr.addEventListener("click", () => renderDetail(tr.getAttribute("data-id"))));
}}

function kv(obj) {{
  const keys = Object.keys(obj).sort();
  if (!keys.length) return `<div class="muted">(none)</div>`;
  return `<div class="kv">${{keys.map(k => `<div class="muted">${{k}}</div><div>${{fmt(obj[k])}}</div>`).join("")}}</div>`;
}}

function renderDetail(id) {{
  const e = DATA.experiments.find((x) => x.id === id);
  if (!e) return;
  const env = e.environment ? `Python ${{e.environment.python}} · ${{e.environment.dependency_count}} deps` : "-";
  const artifacts = e.artifacts.length
    ? e.artifacts.map(a => `<div><code>${{a.path}}</code> <span class="muted">${{shortHash(a.sha256)}} (${{a.size_bytes}} B)</span></div>`).join("")
    : `<div class="muted">(none)</div>`;
  document.getElementById("detail").innerHTML = `
    <div class="detail">
      <h2 style="margin-top:0;font-size:16px;"><code>${{e.id}}</code></h2>
      <h3>Code</h3><div>Git commit: <code>${{fmt(e.git_commit)}}</code></div>
      <h3>Environment</h3><div>${{env}}</div>
      <h3>Parameters</h3>${{kv(e.parameters)}}
      <h3>Execution</h3>
        <div class="kv">
          <div class="muted">command</div><div><code>${{fmt(e.command)}}</code></div>
          <div class="muted">duration</div><div>${{fmt(e.duration_ms)}} ms</div>
          <div class="muted">input_hash</div><div><code>${{shortHash(e.input_hash)}}</code></div>
          <div class="muted">content_hash</div><div><code>${{shortHash(e.content_hash)}}</code></div>
        </div>
      <h3>Outputs</h3>${{artifacts}}
      <h3>Results</h3>${{kv(e.metrics)}}
    </div>`;
  document.getElementById("detail").scrollIntoView({{ behavior: "smooth" }});
}}

renderCards();
renderRows();
</script>
</body>
</html>
"""


def render_dashboard_html(data: dict[str, Any]) -> str:
    """Render the self-contained dashboard HTML for the given data payload."""
    project_name = str(data.get("project", {}).get("name", "project"))
    embedded = json.dumps(data)
    return (
        _HTML_TEMPLATE
        .replace("__PROJECT__", project_name)
        .replace("__DATA__", embedded)
    )


def serve_dashboard(html: str, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Serve a single static HTML page locally (blocking)."""
    body = html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:  # silence default logging
            return

    server = HTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()