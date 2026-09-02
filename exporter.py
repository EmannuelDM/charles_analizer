"""
Exporter for Charles Proxy analyzer results.
Supports exporting to JSON, CSV, interactive HTML report, and dumping raw payloads.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    from .models import CharlesRequest
except ImportError:
    from models import CharlesRequest


class CharlesExporter:
    """Exporter for Charles session data."""

    @staticmethod
    def to_json(requests: List[CharlesRequest], file_path: Union[str, Path], include_bodies: bool = True) -> str:
        """Export requests to a JSON file."""
        data = [r.to_dict(include_bodies=include_bodies) for r in requests]
        out_path = Path(file_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(out_path)

    @staticmethod
    def to_csv(requests: List[CharlesRequest], file_path: Union[str, Path]) -> str:
        """Export tabular metadata of requests to a CSV file."""
        out_path = Path(file_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "id",
            "method",
            "scheme",
            "host",
            "port",
            "path",
            "query",
            "response_status",
            "status_category",
            "duration_ms",
            "latency_ms",
            "request_mime_type",
            "response_mime_type",
            "total_bytes",
            "formatted_size",
            "is_error",
            "url",
        ]

        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in requests:
                d = r.to_dict(include_bodies=False)
                row = {k: d.get(k) for k in fieldnames}
                writer.writerow(row)

        return str(out_path)

    @staticmethod
    def export_payloads(requests: List[CharlesRequest], output_dir: Union[str, Path]) -> str:
        """Dump raw request and response body files to an output directory and generate a manifest.json index."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest = []

        for r in requests:
            if r.req_body_bytes and r.req_filename:
                sub_name = f"{r.id}_req_{r.req_filename}"
                target_file = out_dir / sub_name
                with open(target_file, "wb") as f:
                    f.write(r.req_body_bytes)
                manifest.append({
                    "id": r.id,
                    "type": "request",
                    "filename": sub_name,
                    "size_bytes": len(r.req_body_bytes),
                    "mime_type": r.request_mime_type,
                })

            if r.res_body_bytes and r.res_filename:
                sub_name = f"{r.id}_res_{r.res_filename}"
                target_file = out_dir / sub_name
                with open(target_file, "wb") as f:
                    f.write(r.res_body_bytes)
                manifest.append({
                    "id": r.id,
                    "type": "response",
                    "filename": sub_name,
                    "size_bytes": len(r.res_body_bytes),
                    "mime_type": r.response_mime_type,
                })

        with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        return str(out_dir)

    @classmethod
    def to_html_report(
        cls,
        summary_data: Dict[str, Any],
        requests: List[CharlesRequest],
        file_path: Union[str, Path],
        title: str = "Charles Proxy Session Analysis",
    ) -> str:
        """Generate a sleek, standalone interactive HTML report."""
        out_path = Path(file_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        reqs_json_list = []
        for r in requests:
            item = r.to_dict(include_bodies=True)
            reqs_json_list.append(item)

        json_data_str = json.dumps(reqs_json_list, ensure_ascii=False)
        summary_json_str = json.dumps(summary_data, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --accent-color: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success-color: #4ade80;
            --warning-color: #fbbf24;
            --danger-color: #f87171;
            --badge-bg: #0284c7;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: var(--bg-color); color: var(--text-main); padding: 20px; line-height: 1.5; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; border-bottom: 1px solid var(--card-border); padding-bottom: 15px; }}
        .header h1 {{ font-size: 24px; color: var(--accent-color); font-weight: 700; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }}
        .metric-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        .metric-title {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: var(--text-main); }}
        .controls {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }}
        .search-box {{ flex: 1; min-width: 250px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 6px; padding: 10px 14px; color: #fff; font-size: 14px; outline: none; }}
        .search-box:focus {{ border-color: var(--accent-color); }}
        .filter-btn {{ background: var(--card-bg); border: 1px solid var(--card-border); color: var(--text-muted); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.2s; }}
        .filter-btn.active, .filter-btn:hover {{ background: var(--badge-bg); color: #fff; border-color: var(--accent-color); }}
        .table-container {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
        th {{ background: #162032; padding: 12px 16px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--card-border); }}
        td {{ padding: 12px 16px; border-bottom: 1px solid var(--card-border); color: var(--text-main); word-break: break-all; }}
        tr:hover {{ background: #253346; cursor: pointer; }}
        .status-badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .status-2xx {{ background: #166534; color: #86efac; }}
        .status-3xx {{ background: #854d0e; color: #fef08a; }}
        .status-4xx, .status-5xx, .status-err {{ background: #991b1b; color: #fca5a5; }}
        .method-badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; background: #334155; color: #cbd5e1; }}
        .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }}
        .modal {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; width: 90%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
        .modal-header {{ padding: 16px 20px; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; background: #162032; }}
        .modal-body {{ padding: 20px; overflow-y: auto; flex: 1; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; color: #e2e8f0; }}
        .close-btn {{ background: none; border: none; color: var(--text-muted); font-size: 20px; cursor: pointer; }}
        .close-btn:hover {{ color: #fff; }}

        /* Response Inspector Tabs & JSON Tree */
        .tab-nav {{ display: flex; gap: 4px; border-bottom: 1px solid var(--card-border); margin-bottom: 12px; }}
        .tab-btn {{ padding: 8px 14px; font-size: 12px; font-weight: 600; color: var(--text-muted); background: transparent; border: none; border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.2s; }}
        .tab-btn:hover {{ color: var(--text-main); }}
        .tab-btn.active {{ color: var(--accent-color); border-bottom-color: var(--accent-color); background: rgba(56, 189, 248, 0.08); }}
        .tab-pane {{ display: none; }}
        .tab-pane.active {{ display: block; }}

        .json-tree-container {{ background: #0b0f19; border: 1px solid var(--card-border); border-radius: 8px; padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.6; max-height: 380px; overflow-y: auto; color: #e2e8f0; text-align: left; white-space: normal; }}
        .json-key {{ color: #38bdf8; font-weight: 600; }}
        .json-str {{ color: #4ade80; word-break: break-all; }}
        .json-num {{ color: #fb923c; font-weight: 600; }}
        .json-bool {{ color: #c084fc; font-weight: 600; }}
        .json-null {{ color: #94a3b8; font-style: italic; }}
        .json-bracket {{ color: #94a3b8; font-weight: bold; }}
        .json-toggle {{ cursor: pointer; user-select: none; color: #38bdf8; font-size: 10px; display: inline-block; width: 14px; text-align: center; }}
        .json-toggle:hover {{ color: #7dd3fc; }}
        .json-node {{ margin-left: 18px; border-left: 1px dashed #334155; padding-left: 8px; }}
        .json-line {{ margin: 2px 0; }}
        .json-count {{ font-size: 10px; color: #64748b; margin-left: 4px; font-style: italic; }}
        .json-index {{ color: #64748b; margin-right: 4px; font-size: 10px; }}
        .json-tree-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 10px; flex-wrap: wrap; }}
        .headers-table {{ width: 100%; border-collapse: collapse; font-size: 12px; font-family: monospace; text-align: left; }}
        .headers-table th {{ background: #162032; padding: 8px 12px; color: var(--accent-color); border-bottom: 1px solid var(--card-border); }}
        .headers-table td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <span style="color: var(--text-muted); font-size: 13px;">Generated automatically by Charles Analyzer</span>
    </div>

    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-title">Total Requests</div>
            <div class="metric-value">{summary_data.get('total_requests', 0)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Successful (2xx/3xx)</div>
            <div class="metric-value" style="color: var(--success-color);">{summary_data.get('successful_requests', 0)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Failed / Errors</div>
            <div class="metric-value" style="color: var(--danger-color);">{summary_data.get('failed_requests', 0)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Avg Latency</div>
            <div class="metric-value">{summary_data.get('avg_duration_ms', 0)} ms</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Total Data</div>
            <div class="metric-value">{round(summary_data.get('total_bytes', 0) / 1024, 1)} KB</div>
        </div>
    </div>

    <div class="controls">
        <input type="text" id="searchInput" class="search-box" placeholder="Search URL, method, status, host or body content...">
        <button class="filter-btn active" onclick="filterStatus('all')">All</button>
        <button class="filter-btn" onclick="filterStatus('2xx')">2xx OK</button>
        <button class="filter-btn" onclick="filterStatus('errors')">Errors / 4xx / 5xx</button>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th style="width: 50px;">ID</th>
                    <th style="width: 70px;">Method</th>
                    <th style="width: 70px;">Status</th>
                    <th>Host</th>
                    <th>Path</th>
                    <th style="width: 80px;">Time</th>
                    <th style="width: 90px;">Size</th>
                </tr>
            </thead>
            <tbody id="requestTableBody">
            </tbody>
        </table>
    </div>

    <div class="modal-overlay" id="modalOverlay">
        <div class="modal">
            <div class="modal-header">
                <h3 id="modalTitle">Request Details</h3>
                <button class="close-btn" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalContent"></div>
        </div>
    </div>

    <script>
        const requestsData = {json_data_str};
        let currentFilter = 'all';

        function renderTable(data) {{
            const tbody = document.getElementById('requestTableBody');
            tbody.innerHTML = '';
            
            data.forEach(req => {{
                const tr = document.createElement('tr');
                tr.onclick = () => showDetails(req.id);
                
                let statusClass = 'status-2xx';
                if (req.response_status >= 300 && req.response_status < 400) statusClass = 'status-3xx';
                if (req.is_error || (req.response_status && req.response_status >= 400)) statusClass = 'status-4xx';
                
                const sizeKb = (req.total_bytes / 1024).toFixed(1) + ' KB';
                
                tr.innerHTML = `
                    <td>${{req.id}}</td>
                    <td><span class="method-badge">${{req.method}}</span></td>
                    <td><span class="status-badge ${{statusClass}}">${{req.response_status || 'ERR'}}</span></td>
                    <td>${{req.host}}</td>
                    <td>${{req.path}}</td>
                    <td>${{req.duration_ms}} ms</td>
                    <td>${{sizeKb}}</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function filterStatus(type) {{
            currentFilter = type;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            applyFilters();
        }}

        function applyFilters() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtered = requestsData.filter(req => {{
                let matchesStatus = true;
                if (currentFilter === '2xx') matchesStatus = req.response_status >= 200 && req.response_status < 300;
                if (currentFilter === 'errors') matchesStatus = req.is_error || (req.response_status && req.response_status >= 400);

                const fullUrl = req.url.toLowerCase();
                const host = req.host.toLowerCase();
                const path = req.path.toLowerCase();
                const reqBody = typeof req.request_body === 'string' ? req.request_body.toLowerCase() : JSON.stringify(req.request_body || '').toLowerCase();
                const resBody = typeof req.response_body === 'string' ? req.response_body.toLowerCase() : JSON.stringify(req.response_body || '').toLowerCase();

                const matchesQuery = !query || fullUrl.includes(query) || host.includes(query) || path.includes(query) || reqBody.includes(query) || resBody.includes(query);

                return matchesStatus && matchesQuery;
            }});

            renderTable(filtered);
        }}

        document.getElementById('searchInput').addEventListener('input', applyFilters);

        function generateCurlCommand(req) {{
            let cmd = `curl -X ${{req.method}} "${{req.url}}"`;
            if (req.request_headers) {{
                for (const [k, v] of Object.entries(req.request_headers)) {{
                    cmd += ` \\\n  -H "${{k}}: ${{String(v).replace(/"/g, '\\"')}}"`;
                }}
            }}
            if (req.request_body) {{
                let bodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body) : String(req.request_body);
                cmd += ` \\\n  --data '${{bodyStr.replace(/'/g, "'\\''")}}';
            }}
            return cmd;
        }}

        function copyCurl(id) {{
            const req = requestsData.find(r => r.id === id);
            if (!req) return;
            const curlCmd = generateCurlCommand(req);
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(curlCmd).then(() => alert('Copied cURL command to clipboard! 📋'));
            }} else {{
                const ta = document.createElement('textarea');
                ta.value = curlCmd;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                alert('Copied cURL command to clipboard! 📋');
            }}
        }}

        function remakeRequest(id) {{
            const req = requestsData.find(r => r.id === id);
            if (!req) return;

            const box = document.getElementById('replayResultBox');
            box.style.display = 'block';
            box.innerHTML = '<div style="color: var(--accent-color); font-weight: 600; padding: 10px;">⏳ Replaying request directly from browser...</div>';

            const headers = req.request_headers || {{}};
            let body = req.request_body;
            if (body && typeof body === 'object') body = JSON.stringify(body);

            const options = {{ method: req.method, headers: headers }};
            if (['POST', 'PUT', 'PATCH'].includes(req.method.toUpperCase()) && body) {{
                options.body = body;
            }}

            const t0 = performance.now();
            fetch(req.url, options)
            .then(res => {{
                const t1 = performance.now();
                return res.text().then(text => ({{ status: res.status, headers: [...res.headers.entries()], text, ms: Math.round(t1 - t0) }}));
            }})
            .then(data => {{
                let statusClass = data.status >= 200 && data.status < 400 ? 'status-2xx' : 'status-4xx';
                box.innerHTML = `
                    <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 12px; margin-bottom: 15px;">
                        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 8px;">
                            <span class="status-badge ${{statusClass}}">Status ${{data.status}}</span>
                            <span style="font-size: 12px; color: var(--text-muted);">Replay Duration: <strong>${{data.ms}} ms</strong></span>
                        </div>
                        <div style="font-size: 11px; font-weight: 600; color: var(--accent-color); margin-bottom: 4px;">Replayed Response Headers:</div>
                        <div style="max-height: 100px; overflow-y: auto; font-family: monospace; font-size: 11px; margin-bottom: 8px;">${{JSON.stringify(data.headers, null, 2)}}</div>
                        <div style="font-size: 11px; font-weight: 600; color: var(--accent-color); margin-bottom: 4px;">Replayed Response Body:</div>
                        <div style="max-height: 180px; overflow-y: auto; font-family: monospace; font-size: 11px;">${{data.text}}</div>
                    </div>
                `;
            }})
            .catch(err => {{
                box.innerHTML = `<div style="color: var(--danger-color); font-weight: 600; padding: 10px;">❌ Replay Failed (CORS or network error): ${{err}}</div>`;
            }});
        }}

        function buildJsonTreeHtml(obj) {{
            if (obj === null) return '<span class="json-null">null</span>';
            if (typeof obj === 'boolean') return `<span class="json-bool">${{obj}}</span>`;
            if (typeof obj === 'number') return `<span class="json-num">${{obj}}</span>`;
            if (typeof obj === 'string') {{
                const escaped = obj.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                return `<span class="json-str">"${{escaped}}"</span>`;
            }}
            
            if (Array.isArray(obj)) {{
                if (obj.length === 0) return '<span class="json-bracket">[]</span>';
                let html = `<span class="json-toggle" onclick="toggleJsonNode(this)">▼</span> <span class="json-bracket">[</span> <span class="json-count">${{obj.length}} items</span><div class="json-node">`;
                obj.forEach((item, idx) => {{
                    html += `<div class="json-line"><span class="json-index">${{idx}}:</span> ${{buildJsonTreeHtml(item)}}</div>`;
                }});
                html += `</div><span class="json-bracket">]</span>`;
                return html;
            }}
            
            if (typeof obj === 'object') {{
                const keys = Object.keys(obj);
                if (keys.length === 0) return '<span class="json-bracket">{{}}</span>';
                let html = `<span class="json-toggle" onclick="toggleJsonNode(this)">▼</span> <span class="json-bracket">{{</span> <span class="json-count">${{keys.length}} keys</span><div class="json-node">`;
                keys.forEach(key => {{
                    html += `<div class="json-line"><span class="json-key">"${{key}}"</span>: ${{buildJsonTreeHtml(obj[key])}}</div>`;
                }});
                html += `</div><span class="json-bracket">}}</span>`;
                return html;
            }}
            
            return String(obj);
        }}

        function toggleJsonNode(el) {{
            const parent = el.parentElement;
            const node = parent.querySelector(':scope > .json-node');
            if (node) {{
                if (node.style.display === 'none') {{
                    node.style.display = 'block';
                    el.innerText = '▼';
                }} else {{
                    node.style.display = 'none';
                    el.innerText = '▶';
                }}
            }}
        }}

        function expandAllJson(containerId) {{
            const container = document.getElementById(containerId);
            if (!container) return;
            container.querySelectorAll('.json-node').forEach(n => n.style.display = 'block');
            container.querySelectorAll('.json-toggle').forEach(t => t.innerText = '▼');
        }}

        function collapseAllJson(containerId) {{
            const container = document.getElementById(containerId);
            if (!container) return;
            container.querySelectorAll('.json-node').forEach(n => n.style.display = 'none');
            container.querySelectorAll('.json-toggle').forEach(t => t.innerText = '▶');
        }}

        function filterJsonTree(query, containerId) {{
            const container = document.getElementById(containerId);
            if (!container) return;
            const q = query.toLowerCase().trim();
            const lines = container.querySelectorAll('.json-line');
            if (!q) {{
                lines.forEach(l => l.style.display = 'block');
                return;
            }}
            lines.forEach(l => {{
                const text = l.innerText.toLowerCase();
                if (text.includes(q)) {{
                    l.style.display = 'block';
                    let p = l.parentElement;
                    while (p && p !== container) {{
                        if (p.classList.contains('json-node')) p.style.display = 'block';
                        p = p.parentElement;
                    }}
                }} else {{
                    l.style.display = 'none';
                }}
            }});
        }}

        function renderHeadersTable(headersObj) {{
            if (!headersObj || Object.keys(headersObj).length === 0) {{
                return '<div style="color: var(--text-muted); font-style: italic; padding: 8px;">No headers available</div>';
            }}
            let html = `
                <table class="headers-table">
                    <thead>
                        <tr>
                            <th style="width: 35%;">Header Name</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>`;
            for (const [k, v] of Object.entries(headersObj)) {{
                const lowerK = k.toLowerCase();
                const isAuth = ['authorization', 'cookie', 'set-cookie', 'x-auth-token', 'token'].includes(lowerK);
                const keyStyle = isAuth ? 'color: #38bdf8; font-weight: 700;' : 'color: #9ca3af;';
                const valStyle = isAuth ? 'color: #fb923c; font-weight: 600;' : 'color: #e2e8f0;';
                const badgeStr = isAuth ? ' <span class="status-badge status-3xx" style="font-size:9px; padding:1px 4px;">AUTH</span>' : '';
                html += `
                    <tr>
                        <td style="${{keyStyle}}">${{k}}${{badgeStr}}</td>
                        <td style="${{valStyle}}">${{v}}</td>
                    </tr>`;
            }}
            html += '</tbody></table>';
            return html;
        }}

        function switchTab(groupName, tabIndex) {{
            document.querySelectorAll(`.tab-btn-${{groupName}}`).forEach((btn, idx) => {{
                if (idx === tabIndex) {{
                    btn.classList.add('active');
                }} else {{
                    btn.classList.remove('active');
                }}
            }});
            document.querySelectorAll(`.tab-pane-${{groupName}}`).forEach((pane, idx) => {{
                if (idx === tabIndex) {{
                    pane.classList.add('active');
                }} else {{
                    pane.classList.remove('active');
                }}
            }});
        }}

        function copyResponseBody(reqId) {{
            const req = requestsData.find(r => r.id === reqId);
            if (!req || !req.response_body) return;
            const text = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : String(req.response_body);
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(() => showToast('Copied Response Body to clipboard! 📋'));
            }} else {{
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                showToast('Copied Response Body to clipboard! 📋');
            }}
        }}

        function downloadResponseBody(reqId) {{
            const req = requestsData.find(r => r.id === reqId);
            if (!req || !req.response_body) return;
            const isObj = typeof req.response_body === 'object';
            const text = isObj ? JSON.stringify(req.response_body, null, 2) : String(req.response_body);
            const blob = new Blob([text], {{ type: isObj ? 'application/json' : 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `response_req_${{req.id}}.${{isObj ? 'json' : 'txt'}}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('Downloaded response body file! 💾');
        }}

        function showDetails(id) {{
            const req = requestsData.find(r => r.id === id);
            if (!req) return;

            document.getElementById('modalTitle').innerText = `#${{req.id}} - ${{req.method}} ${{req.url}}`;
            const curlCmd = generateCurlCommand(req);

            let reqBodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body, null, 2) : (req.request_body || 'No Request Body');
            let resBodyStr = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : (req.response_body || 'No Response Body');

            let resTreeHtml = typeof req.response_body === 'object' ? buildJsonTreeHtml(req.response_body) : (req.response_body ? `<div class="json-str">${{req.response_body}}</div>` : '<div style="color:var(--text-muted);">No Response Body</div>');
            let reqTreeHtml = typeof req.request_body === 'object' ? buildJsonTreeHtml(req.request_body) : (req.request_body ? `<div class="json-str">${{req.request_body}}</div>` : '<div style="color:var(--text-muted);">No Request Body</div>');

            let resHeadersHtml = renderHeadersTable(req.response_headers);
            let reqHeadersHtml = renderHeadersTable(req.request_headers);

            let statusBadgeClass = req.response_status >= 200 && req.response_status < 300 ? 'status-2xx' : (req.response_status >= 300 && req.response_status < 400 ? 'status-3xx' : 'status-4xx');

            let html = `
                <div style="display: flex; justify-content: space-between; align-items: center; background: #0f172a; padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; flex-wrap: wrap; gap: 10px;">
                    <div style="font-size: 12px; display: flex; gap: 12px; align-items: center;">
                        <span class="status-badge ${{statusBadgeClass}}">${{req.response_status}} ${{req.status_text || ''}}</span>
                        <span>Duration: <strong>${{req.duration_ms}} ms</strong></span>
                        <span>Size: <strong>${{req.total_bytes}} bytes</strong></span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="filter-btn" style="background: var(--badge-bg); color: #fff;" onclick="remakeRequest(${{req.id}})">🔄 Do request</button>
                        <button class="filter-btn" onclick="copyCurl(${{req.id}})">📋 Copy cURL</button>
                        <button class="filter-btn" onclick="copyResponseBody(${{req.id}})">📋 Copy Body</button>
                        <button class="filter-btn" onclick="downloadResponseBody(${{req.id}})">💾 Download</button>
                    </div>
                </div>

                <div id="replayResultBox" style="display: none;"></div>

                <!-- RESPONSE VISUALIZATION SECTION -->
                <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px; margin-bottom: 15px;">
                    <h3 style="color: var(--accent-color); font-size: 14px; font-weight: 700; margin-bottom: 10px;">📡 Response Inspector</h3>

                    <div class="tab-nav">
                        <button class="tab-btn tab-btn-res active" onclick="switchTab('res', 0)">🌳 Interactive JSON Tree</button>
                        <button class="tab-btn tab-btn-res" onclick="switchTab('res', 1)">📄 Raw Body</button>
                        <button class="tab-btn tab-btn-res" onclick="switchTab('res', 2)">📋 Response Headers (${{req.response_headers ? Object.keys(req.response_headers).length : 0}})</button>
                    </div>

                    <div class="tab-pane tab-pane-res active">
                        <div class="json-tree-bar">
                            <input type="text" class="search-box" style="padding: 4px 10px; font-size: 12px; width: 220px;" placeholder="🔍 Search JSON..." oninput="filterJsonTree(this.value, 'resTreeBox')">
                            <div style="display: flex; gap: 4px;">
                                <button class="filter-btn" style="padding: 2px 8px; font-size: 10px;" onclick="expandAllJson('resTreeBox')">Expand All</button>
                                <button class="filter-btn" style="padding: 2px 8px; font-size: 10px;" onclick="collapseAllJson('resTreeBox')">Collapse All</button>
                            </div>
                        </div>
                        <div id="resTreeBox" class="json-tree-container">${{resTreeHtml}}</div>
                    </div>

                    <div class="tab-pane tab-pane-res">
                        <div style="background: #0f172a; border: 1px solid var(--card-border); padding: 10px; border-radius: 6px; max-height: 250px; overflow-y: auto;">${{resBodyStr}}</div>
                    </div>

                    <div class="tab-pane tab-pane-res">
                        ${{resHeadersHtml}}
                    </div>
                </div>

                <!-- REQUEST DETAILS SECTION -->
                <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px;">
                    <h3 style="color: var(--accent-color); font-size: 14px; font-weight: 700; margin-bottom: 10px;">📤 Request Details</h3>

                    <div class="tab-nav">
                        <button class="tab-btn tab-btn-req active" onclick="switchTab('req', 0)">⚡ cURL Command</button>
                        <button class="tab-btn tab-btn-req" onclick="switchTab('req', 1)">📋 Request Headers (${{req.request_headers ? Object.keys(req.request_headers).length : 0}})</button>
                        <button class="tab-btn tab-btn-req" onclick="switchTab('req', 2)">📦 Payload Body</button>
                    </div>

                    <div class="tab-pane tab-pane-req active">
                        <div style="background: #0f172a; border: 1px solid var(--card-border); padding: 10px; border-radius: 6px; color: #a5f3fc; max-height: 120px; overflow-y: auto;">${{curlCmd}}</div>
                    </div>

                    <div class="tab-pane tab-pane-req">
                        ${{reqHeadersHtml}}
                    </div>

                    <div class="tab-pane tab-pane-req">
                        <div class="json-tree-container">${{reqTreeHtml}}</div>
                    </div>
                </div>
            `;

            document.getElementById('modalContent').innerHTML = html;
            document.getElementById('modalOverlay').style.display = 'flex';
        }}

        function closeModal() {{
            document.getElementById('modalOverlay').style.display = 'none';
        }}

        // Close modal on Escape key
        window.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeModal();
        }});

        // Close modal on backdrop overlay click
        document.getElementById('modalOverlay').addEventListener('click', function(e) {{
            if (e.target.id === 'modalOverlay') closeModal();
        }});

        renderTable(requestsData);
    </script>
</body>
</html>"""

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return str(out_path)
