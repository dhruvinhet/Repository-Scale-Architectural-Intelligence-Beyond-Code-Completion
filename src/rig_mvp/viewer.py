from __future__ import annotations

from functools import partial
import http.server
import json
from pathlib import Path
import socketserver
import webbrowser


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RIG Viewer</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network@9.1.9/dist/vis-network.min.js"></script>
  <style>
    html, body { margin: 0; height: 100%; font-family: Arial, sans-serif; }
    #toolbar { padding: 10px; border-bottom: 1px solid #ddd; display: flex; gap: 12px; align-items: center; }
    #graph { width: 100%; height: calc(100% - 46px); }
    .badge { padding: 2px 8px; background: #f2f2f2; border-radius: 10px; font-size: 12px; }
  </style>
</head>
<body>
  <div id="toolbar">
    <strong>Repository Intelligence Graph</strong>
    <span class="badge">Nodes: __NODE_COUNT__</span>
    <span class="badge">Edges: __EDGE_COUNT__</span>
  </div>
  <div id="graph"></div>
  <script>
    const graphData = __GRAPH_DATA__;

    const kindColor = {
      Target: "#4f46e5",
      Module: "#059669",
      Class: "#7c3aed",
      Function: "#db2777",
      Test: "#ea580c",
      ExternalDependency: "#0f766e",
    };

    const nodes = new vis.DataSet(graphData.nodes.map(n => ({
      id: n.id,
      label: n.name,
      title: `${n.kind}\n${(n.evidence || []).join("\\n")}`,
      color: kindColor[n.kind] || "#334155",
      shape: "dot",
      size: 10,
      font: { size: 12 }
    })));

    const edges = new vis.DataSet(graphData.edges.map((e, index) => ({
      id: index + 1,
      from: e.source,
      to: e.target,
      label: e.relation,
      arrows: "to",
      font: { align: "middle", size: 10 },
      color: { color: "#94a3b8" }
    })));

    const container = document.getElementById("graph");
    const data = { nodes, edges };
    const options = {
      interaction: { hover: true, navigationButtons: true, keyboard: true },
      physics: { stabilization: true, barnesHut: { springLength: 140 } },
      edges: { smooth: { type: "dynamic" } }
    };

    new vis.Network(container, data, options);
  </script>
</body>
</html>
"""


WORKFLOW_HTML_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>RIG Workflow Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --border: #e2e8f0;
      --ok: #166534;
      --warn: #b45309;
      --err: #b91c1c;
      --decomposer: #1d4ed8;
      --generator: #6d28d9;
      --critic: #b45309;
      --repair: #0f766e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 20px;
      font-family: Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    h1, h2 { margin: 0 0 12px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
    }
    .metric {
      font-size: 24px;
      font-weight: 700;
      margin-top: 4px;
    }
    .muted { color: var(--muted); }
    .status-ok { color: var(--ok); font-weight: 700; }
    .status-warn { color: var(--warn); font-weight: 700; }
    .status-err { color: var(--err); font-weight: 700; }
    .task-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      color: white;
      margin-right: 6px;
    }
    .decomposer { background: var(--decomposer); }
    .generator { background: var(--generator); }
    .critic { background: var(--critic); }
    .repair { background: var(--repair); }
    ul { margin: 8px 0 0 20px; padding: 0; }
    li { margin: 4px 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    th, td {
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
      font-size: 13px;
    }
    th { background: #f1f5f9; }
    code {
      background: #f1f5f9;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 1px 6px;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <h1>Intent + Agent Workflow Viewer</h1>
  <p class=\"muted\">Intent decomposition, logic fragmentation, and multi-agent execution trace.</p>

  <div class=\"grid\">
    <div class=\"card\">
      <div class=\"muted\">Intent</div>
      <div class=\"metric\" style=\"font-size:18px\">__INTENT__</div>
    </div>
    <div class=\"card\">
      <div class=\"muted\">Subtasks</div>
      <div class=\"metric\">__TASK_COUNT__</div>
    </div>
    <div class=\"card\">
      <div class=\"muted\">Executions</div>
      <div class=\"metric\">__EXEC_COUNT__</div>
    </div>
    <div class=\"card\">
      <div class=\"muted\">Verification</div>
      <div class=\"metric __VERIFY_CLASS__\">__VERIFY_STATUS__</div>
      <div class=\"muted\">Rounds: __VERIFY_ROUNDS__</div>
    </div>
  </div>

  <h2>Intent Fragmentation (Plan)</h2>
  <div class=\"task-list\">__PLAN_TASKS__</div>

  <h2 style=\"margin-top:18px\">Agent Execution Trace</h2>
  <div class=\"task-list\">__EXEC_TASKS__</div>

  <h2 style=\"margin-top:18px\">Verification Steps</h2>
  <table>
    <thead>
      <tr>
        <th>Step</th>
        <th>Status</th>
        <th>Exit</th>
        <th>Duration (ms)</th>
        <th>Command</th>
      </tr>
    </thead>
    <tbody>
      __VERIFY_ROWS__
    </tbody>
  </table>
</body>
</html>
"""


def build_html_view(rig_json_path: Path, out_html_path: Path) -> Path:
    payload = json.loads(rig_json_path.read_text(encoding="utf-8"))

    html = HTML_TEMPLATE.replace("__GRAPH_DATA__", json.dumps(payload))
    html = html.replace("__NODE_COUNT__", str(payload.get("metadata", {}).get("node_count", 0)))
    html = html.replace("__EDGE_COUNT__", str(payload.get("metadata", {}).get("edge_count", 0)))

    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(html, encoding="utf-8")
    return out_html_path


def build_workflow_html_view(
    plan_json_path: Path,
    generate_report_path: Path,
    out_html_path: Path,
 ) -> Path:
    plan = json.loads(plan_json_path.read_text(encoding="utf-8"))
    report = json.loads(generate_report_path.read_text(encoding="utf-8"))

    intent = str(plan.get("intent") or report.get("intent") or "<unknown>")
    subtasks = plan.get("subtasks", []) if isinstance(plan.get("subtasks", []), list) else []
    executions = report.get("executions", []) if isinstance(report.get("executions", []), list) else []

    verification = report.get("verification", {}) if isinstance(report.get("verification", {}), dict) else {}
    verification_passed = bool(verification.get("passed", False))
    verify_status = "PASSED" if verification_passed else "FAILED"
    verify_class = "status-ok" if verification_passed else "status-err"
    verify_rounds = verification.get("rounds", 0)

    plan_cards: list[str] = []
    for task in subtasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "?"))
        title = str(task.get("title", "<no title>"))
        role = str(task.get("agent_role", "generator"))
        role_class = role if role in {"decomposer", "generator", "critic", "repair"} else "generator"
        hints = task.get("impacted_hints", []) if isinstance(task.get("impacted_hints", []), list) else []
        criteria = task.get("acceptance_criteria", []) if isinstance(task.get("acceptance_criteria", []), list) else []

        hints_html = "".join(f"<li><code>{_esc(str(item))}</code></li>" for item in hints[:6]) or "<li class=\"muted\">No hints</li>"
        criteria_html = "".join(f"<li>{_esc(str(item))}</li>" for item in criteria[:6]) or "<li class=\"muted\">No criteria</li>"

        plan_cards.append(
            "".join(
                [
                    '<div class="card">',
                    f'<div><strong>{_esc(task_id)}: {_esc(title)}</strong></div>',
                    f'<div style="margin-top:6px"><span class="pill {role_class}">{_esc(role)}</span></div>',
                    '<div style="margin-top:8px" class="muted">Impacted hints</div>',
                    f"<ul>{hints_html}</ul>",
                    '<div style="margin-top:8px" class="muted">Acceptance criteria</div>',
                    f"<ul>{criteria_html}</ul>",
                    "</div>",
                ]
            )
        )

    exec_cards: list[str] = []
    for item in executions:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id", "?"))
        title = str(item.get("title", "<no title>"))
        status = str(item.get("status", "unknown"))
        status_class = "status-ok" if status == "completed" else "status-warn"
        actions = item.get("actions", []) if isinstance(item.get("actions", []), list) else []
        candidates = item.get("candidate_files", []) if isinstance(item.get("candidate_files", []), list) else []
        applied = item.get("applied_files", []) if isinstance(item.get("applied_files", []), list) else []
        skipped = item.get("skipped_files", []) if isinstance(item.get("skipped_files", []), list) else []

        actions_html = "".join(f"<li>{_esc(str(a))}</li>" for a in actions[:8]) or "<li class=\"muted\">No actions</li>"
        candidate_html = "".join(f"<li><code>{_esc(str(c))}</code></li>" for c in candidates[:6]) or "<li class=\"muted\">No candidates</li>"
        applied_html = "".join(f"<li><code>{_esc(str(a))}</code></li>" for a in applied[:6]) or "<li class=\"muted\">No applied files</li>"
        skipped_html = "".join(f"<li><code>{_esc(str(s))}</code></li>" for s in skipped[:6]) or "<li class=\"muted\">No skipped files</li>"

        exec_cards.append(
            "".join(
                [
                    '<div class="card">',
                    f'<div><strong>{_esc(task_id)}: {_esc(title)}</strong></div>',
                    f'<div style="margin-top:6px">Status: <span class="{status_class}">{_esc(status)}</span></div>',
                    '<div style="margin-top:8px" class="muted">Actions</div>',
                    f"<ul>{actions_html}</ul>",
                    '<div style="margin-top:8px" class="muted">Candidate files</div>',
                    f"<ul>{candidate_html}</ul>",
                    '<div style="margin-top:8px" class="muted">Applied files</div>',
                    f"<ul>{applied_html}</ul>",
                    '<div style="margin-top:8px" class="muted">Skipped files</div>',
                    f"<ul>{skipped_html}</ul>",
                    "</div>",
                ]
            )
        )

    verify_rows: list[str] = []
    for step in verification.get("steps", []) if isinstance(verification.get("steps", []), list) else []:
        if not isinstance(step, dict):
            continue
        step_name = _esc(str(step.get("name", "")))
        status = _esc(str(step.get("status", "")))
        exit_code = _esc(str(step.get("exit_code", "")))
        duration_ms = _esc(str(step.get("duration_ms", "")))
        command = _esc(str(step.get("command", "")))
        verify_rows.append(
            "".join(
                [
                    "<tr>",
                    f"<td>{step_name}</td>",
                    f"<td>{status}</td>",
                    f"<td>{exit_code}</td>",
                    f"<td>{duration_ms}</td>",
                    f"<td><code>{command}</code></td>",
                    "</tr>",
                ]
            )
        )

    html = WORKFLOW_HTML_TEMPLATE
    html = html.replace("__INTENT__", _esc(intent))
    html = html.replace("__TASK_COUNT__", str(len(subtasks)))
    html = html.replace("__EXEC_COUNT__", str(len(executions)))
    html = html.replace("__VERIFY_STATUS__", verify_status)
    html = html.replace("__VERIFY_CLASS__", verify_class)
    html = html.replace("__VERIFY_ROUNDS__", _esc(str(verify_rounds)))
    html = html.replace("__PLAN_TASKS__", "".join(plan_cards) or '<div class="card muted">No plan tasks available.</div>')
    html = html.replace("__EXEC_TASKS__", "".join(exec_cards) or '<div class="card muted">No execution records available.</div>')
    html = html.replace("__VERIFY_ROWS__", "".join(verify_rows) or '<tr><td colspan="5" class="muted">No verification steps available.</td></tr>')

    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(html, encoding="utf-8")
    return out_html_path


def serve_html(html_path: Path, host: str = "127.0.0.1", port: int = 8000, open_browser: bool = False) -> str:
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    directory = html_path.parent.resolve()
    target = html_path.name
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))

    with socketserver.TCPServer((host, port), handler) as server:
        url = f"http://{host}:{port}/{target}"
        if open_browser:
            webbrowser.open(url)
        print(f"Serving RIG viewer at: {url}")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return url


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
