"""
Web Application and Server for Charles Proxy Analyzer.
Provides interactive SPA for trace analysis, JSON tree inspection, replay, and structure tree view.
"""

import base64
import json
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Any, List

pkg_dir = Path(__file__).resolve().parent
parent_dir = pkg_dir.parent

if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

try:
    from .analyzer import CharlesAnalyzer
    from .exporter import CharlesExporter
except ImportError:
    try:
        from charles_analizer.analyzer import CharlesAnalyzer
        from charles_analizer.exporter import CharlesExporter
    except ImportError:
        from analyzer import CharlesAnalyzer
        from exporter import CharlesExporter

# Global reference to current loaded analyzer session
CURRENT_ANALYZER: CharlesAnalyzer = None


def get_example_file_path() -> Path:
    candidates = [
        Path(__file__).parent / "example_1.chlz",
        Path.cwd() / "example_1.chlz",
        Path("charles_analizer/example_1.chlz"),
        Path(__file__).parent / "charles_analizer" / "example_1.chlz",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(__file__).parent / "example_1.chlz"


class CharlesWebHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Charles Proxy Web Application."""

    def log_message(self, format, *args):
        """Custom clean logging."""
        sys.stdout.write(f"[WebServer] {args[0]}\n")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, content: bytes, content_type: str, filename: str = None):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", content_type)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_export_html(self):
        try:
            if not CURRENT_ANALYZER:
                self._send_json({"error": "No session loaded"}, status=400)
                return

            temp_path = Path("/tmp/charles_report.html")
            s = CURRENT_ANALYZER.summary()
            out_file = CharlesExporter.to_html_report(s, CURRENT_ANALYZER.requests, temp_path)

            with open(out_file, "rb") as f:
                content = f.read()

            self._send_file(content, "text/html; charset=utf-8", filename="charles_report.html")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, status=500)
            except Exception:
                pass

    def _handle_export_json(self):
        try:
            if not CURRENT_ANALYZER:
                self._send_json({"error": "No session loaded"}, status=400)
                return
            data = [r.to_dict(include_bodies=True) for r in CURRENT_ANALYZER.requests]
            content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            self._send_file(content, "application/json", filename="charles_session.json")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, status=500)
            except Exception:
                pass

    def _handle_export_csv(self):
        try:
            if not CURRENT_ANALYZER:
                self._send_json({"error": "No session loaded"}, status=400)
                return
            temp_csv = Path("/tmp/charles_session.csv")
            CharlesExporter.to_csv(CURRENT_ANALYZER.requests, temp_csv)
            with open(temp_csv, "rb") as f:
                content = f.read()
            self._send_file(content, "text/csv", filename="charles_session.csv")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, status=500)
            except Exception:
                pass

    def do_GET(self):
        """Serve frontend SPA or static assets."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ["/", "/index.html"]:
            html_content = self.render_web_app_html()
            self._send_file(html_content.encode("utf-8"), "text/html; charset=utf-8")
        elif path in ["/inspector", "/inspector.html"]:
            html_content = self.render_full_tab_inspector_html()
            self._send_file(html_content.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/status":
            global CURRENT_ANALYZER
            loaded = CURRENT_ANALYZER is not None
            self._send_json({"status": "ok", "file_loaded": loaded})
        elif path == "/api/summary":
            if not CURRENT_ANALYZER:
                self._send_json({"error": "No session loaded"}, status=400)
            else:
                self._send_json({"success": True, "summary": CURRENT_ANALYZER.summary()})
        elif path == "/api/export/html":
            self._handle_export_html()
        elif path == "/api/export/json":
            self._handle_export_json()
        elif path == "/api/export/csv":
            self._handle_export_csv()
        elif path == "/api/request":
            query = urllib.parse.parse_qs(parsed_url.query)
            req_id_str = query.get("id", [None])[0]
            if not CURRENT_ANALYZER or not req_id_str:
                self._send_json({"error": "Request not found or no session loaded"}, status=404)
            else:
                try:
                    req_id = int(req_id_str)
                    r = next((req for req in CURRENT_ANALYZER.requests if req.id == req_id), None)
                    if r:
                        self._send_json({"success": True, "request": r.to_dict(include_bodies=True)})
                    else:
                        self._send_json({"error": f"Request #{req_id} not found"}, status=404)
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        """Handle upload, analysis, and report generation APIs."""
        global CURRENT_ANALYZER

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        if self.path == "/api/example":
            try:
                example_path = get_example_file_path()
                if not example_path.exists():
                    self._send_json({"error": "Example file example_1.chlz not found"}, status=404)
                    return
                CURRENT_ANALYZER = CharlesAnalyzer.from_file(example_path)
                summary = CURRENT_ANALYZER.summary()
                requests_data = [r.to_dict(include_bodies=True) for r in CURRENT_ANALYZER.requests]
                self._send_json({
                    "success": True,
                    "filename": "example_1.chlz",
                    "summary": summary,
                    "requests": requests_data,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)

        elif self.path == "/api/upload":
            try:
                if self.headers.get("Content-Type", "").startswith("application/json"):
                    payload = json.loads(post_data.decode("utf-8"))
                    filename = payload.get("filename", "session.chlz")
                    file_b64 = payload.get("file_b64", "")
                    file_bytes = base64.b64decode(file_b64)
                else:
                    filename = "uploaded_session.chlz"
                    file_bytes = post_data

                CURRENT_ANALYZER = CharlesAnalyzer.from_file(file_bytes)
                summary = CURRENT_ANALYZER.summary()
                requests_data = [r.to_dict(include_bodies=True) for r in CURRENT_ANALYZER.requests]

                self._send_json({
                    "success": True,
                    "filename": filename,
                    "summary": summary,
                    "requests": requests_data,
                })
            except Exception as e:
                self._send_json({"error": f"Failed to parse .chlz file: {str(e)}"}, status=400)

        elif self.path == "/api/export/html":
            self._handle_export_html()

        elif self.path == "/api/export/json":
            self._handle_export_json()

        elif self.path == "/api/export/csv":
            self._handle_export_csv()

        elif self.path == "/api/replay":
            try:
                import urllib.request
                import urllib.error
                import time
                import gzip
                import zlib

                payload = json.loads(post_data.decode("utf-8"))
                target_url = payload.get("url")
                method = payload.get("method", "GET").upper()
                headers = payload.get("headers", {})
                req_body = payload.get("body")

                body_bytes = None
                if req_body:
                    if isinstance(req_body, (dict, list)):
                        body_bytes = json.dumps(req_body).encode("utf-8")
                        if "Content-Type" not in headers and "content-type" not in headers:
                            headers["Content-Type"] = "application/json"
                    else:
                        body_bytes = str(req_body).encode("utf-8")

                req = urllib.request.Request(target_url, data=body_bytes, headers=headers, method=method)
                t0 = time.time()

                def _decompress_payload(raw_bytes: bytes, resp_headers: dict) -> str:
                    if not raw_bytes:
                        return ""
                    encoding = (resp_headers.get("Content-Encoding") or resp_headers.get("content-encoding") or "").lower()
                    if "gzip" in encoding or raw_bytes.startswith(b"\x1f\x8b"):
                        try:
                            raw_bytes = gzip.decompress(raw_bytes)
                        except Exception:
                            pass
                    elif "deflate" in encoding:
                        try:
                            raw_bytes = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)
                        except Exception:
                            try:
                                raw_bytes = zlib.decompress(raw_bytes)
                            except Exception:
                                pass
                    elif "br" in encoding:
                        try:
                            import brotli
                            raw_bytes = brotli.decompress(raw_bytes)
                        except Exception:
                            pass
                    return raw_bytes.decode("utf-8", errors="replace")

                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        duration_ms = int((time.time() - t0) * 1000)
                        resp_headers = dict(resp.headers)
                        res_body_text = _decompress_payload(resp.read(), resp_headers)
                        try:
                            res_body_json = json.loads(res_body_text)
                        except Exception:
                            res_body_json = res_body_text
                        self._send_json({
                            "success": True,
                            "status": resp.status,
                            "headers": resp_headers,
                            "body": res_body_json,
                            "duration_ms": duration_ms
                        })
                except urllib.error.HTTPError as e:
                    duration_ms = int((time.time() - t0) * 1000)
                    resp_headers = dict(e.headers)
                    res_body_text = _decompress_payload(e.read(), resp_headers)
                    try:
                        res_body_json = json.loads(res_body_text)
                    except Exception:
                        res_body_json = res_body_text
                    self._send_json({
                        "success": True,
                        "status": e.code,
                        "headers": resp_headers,
                        "body": res_body_json,
                        "duration_ms": duration_ms
                    })
            except Exception as e:
                self._send_json({"error": f"Replay failed: {str(e)}"}, status=500)
        else:
            self.send_error(404, "Endpoint Not Found")

    def render_full_tab_inspector_html(self) -> str:
        """Render full page standalone inspector HTML/JS/CSS."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Charles Request Inspector</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --surface: #111827;
            --card-bg: #1f2937;
            --card-border: #374151;
            --card-hover: #2d3748;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.25);
            --accent: #a855f7;
            --text: #f9fafb;
            --text-secondary: #9ca3af;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --radius: 12px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 16px 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid transparent;
            text-decoration: none;
            transition: all 0.2s;
        }
        .btn-primary { background: linear-gradient(135deg, #0284c7, #7e22ce); color: #fff; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3); }
        .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(2, 132, 199, 0.5); }
        .btn-secondary { background: var(--card-bg); border-color: var(--card-border); color: var(--text); }
        .btn-secondary:hover { border-color: var(--primary); color: var(--primary); }
        
        .code-box {
            background: var(--bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #e5e7eb;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            overflow-y: auto;
        }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 12px; }
        .badge-2xx { background: rgba(52, 211, 153, 0.2); color: var(--success); }
        .badge-3xx { background: rgba(251, 191, 36, 0.2); color: var(--warning); }
        .badge-4xx, .badge-err { background: rgba(248, 113, 113, 0.2); color: var(--danger); }
        
        .tab-nav { display: flex; gap: 4px; border-bottom: 1px solid var(--card-border); margin-bottom: 16px; }
        .tab-btn { padding: 10px 18px; font-size: 13px; font-weight: 600; color: var(--text-secondary); background: transparent; border: none; border-bottom: 2px solid transparent; cursor: pointer; }
        .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }

        .json-tree-container { background: var(--bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px; font-family: 'JetBrains Mono', monospace; font-size: 12px; max-height: 450px; overflow-y: auto; }
        .json-item { margin-left: 14px; }
        .json-key { color: #38bdf8; font-weight: 600; }
        .json-str { color: #34d399; }
        .json-num { color: #f63665; }
        .json-bool { color: #c084fc; font-weight: 700; }
        .json-null { color: #9ca3af; font-style: italic; }
        .json-toggle { cursor: pointer; user-select: none; color: #94a3b8; font-weight: 700; margin-right: 4px; }
        
        .param-input, .param-select, .param-textarea { background: var(--bg); border: 1px solid var(--card-border); border-radius: 6px; padding: 8px 12px; color: #fff; font-size: 13px; font-family: inherit; width: 100%; }
        .param-input:focus, .param-select:focus, .param-textarea:focus { border-color: var(--primary); outline: none; }
        .kv-row { display: flex; gap: 8px; margin-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        th { background: #161e2e; padding: 10px 14px; color: var(--text-secondary); font-weight: 600; border-bottom: 1px solid var(--card-border); }
        td { padding: 10px 14px; border-bottom: 1px solid var(--card-border); word-break: break-all; }
    </style>
</head>
<body>
    <header>
        <div style="display: flex; align-items: center; gap: 12px;">
            <a href="/" class="btn btn-secondary">⬅️ Back to Main Dashboard</a>
            <h1 id="pageTitle" style="font-size: 17px; font-weight: 700; color: var(--primary);">Loading Request Inspector...</h1>
        </div>
        <div style="display: flex; gap: 10px;">
            <button class="btn btn-primary" onclick="doReplayFromFullTab()">🔄 Do request</button>
            <button class="btn btn-secondary" onclick="copyFullCurl()">📋 Copy cURL</button>
        </div>
    </header>

    <div id="inspectorContent" style="display: flex; flex-direction: column; gap: 20px;">
        <div style="padding: 24px; text-align: center; color: var(--text-secondary);">⏳ Loading request details...</div>
    </div>

    <script>
        let currentRequestData = null;

        function buildJsonTreeHtml(obj) {
            if (obj === null) return '<span class="json-null">null</span>';
            if (typeof obj === 'number') return `<span class="json-num">${obj}</span>`;
            if (typeof obj === 'boolean') return `<span class="json-bool">${obj}</span>`;
            if (typeof obj === 'string') return `<span class="json-str">"${escapeHtml(obj)}"</span>`;

            const isArray = Array.isArray(obj);
            const keys = Object.keys(obj);
            if (keys.length === 0) return isArray ? '[]' : '{}';

            let html = `<span class="json-toggle" onclick="toggleJsonNode(this)">▼</span><span>${isArray ? '[' : '{'}</span><div class="json-node-content">`;
            keys.forEach((key, idx) => {
                const val = obj[key];
                const comma = idx < keys.length - 1 ? ',' : '';
                html += `<div class="json-item">`;
                if (!isArray) html += `<span class="json-key">"${escapeHtml(key)}"</span>: `;
                html += buildJsonTreeHtml(val) + comma + `</div>`;
            });
            html += `</div><span>${isArray ? ']' : '}'}</span>`;
            return html;
        }

        function toggleJsonNode(el) {
            const content = el.nextElementSibling.nextElementSibling;
            if (content.style.display === 'none') {
                content.style.display = 'block';
                el.innerText = '▼';
            } else {
                content.style.display = 'none';
                el.innerText = '▶';
            }
        }

        function escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function generateCurlCommand(req) {
            let cmd = `curl -X ${req.method} "${req.url}"`;
            if (req.request_headers) {
                for (const [k, v] of Object.entries(req.request_headers)) {
                    cmd += ` \\\n  -H "${k}: ${String(v).replace(/"/g, '\\"')}"`;
                }
            }
            if (req.request_body) {
                let bodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body) : String(req.request_body);
                cmd += ` \\\n  --data '${bodyStr.replace(/'/g, "'\\''")}'`;
            }
            return cmd;
        }

        function copyFullCurl() {
            if (!currentRequestData) return;
            const cmd = generateCurlCommand(currentRequestData);
            navigator.clipboard.writeText(cmd).then(() => alert('Copied cURL command to clipboard! 📋'));
        }

        function switchTab(group, index) {
            const btns = document.querySelectorAll('.tab-btn-' + group);
            const panes = document.querySelectorAll('.tab-pane-' + group);
            btns.forEach((b, i) => b.classList.toggle('active', i === index));
            panes.forEach((p, i) => p.classList.toggle('active', i === index));
        }

        function addHeaderRow(key = '', val = '') {
            const container = document.getElementById('headersEditorContainer');
            if (!container) return;
            const row = document.createElement('div');
            row.className = 'kv-row';
            row.innerHTML = `
                <input type="text" class="param-input kv-key-input" placeholder="Header Name" value="${escapeHtml(key)}">
                <input type="text" class="param-input kv-val-input" placeholder="Header Value" value="${escapeHtml(val)}">
                <button type="button" class="btn btn-secondary" style="padding: 4px 10px;" onclick="this.parentElement.remove()">🗑️</button>
            `;
            container.appendChild(row);
        }

        function doReplayFromFullTab() {
            const method = document.getElementById('editMethod') ? document.getElementById('editMethod').value : (currentRequestData ? currentRequestData.method : 'GET');
            const url = document.getElementById('editUrl') ? document.getElementById('editUrl').value : (currentRequestData ? currentRequestData.url : '');
            
            const headers = {};
            const keyInputs = document.querySelectorAll('.kv-key-input');
            const valInputs = document.querySelectorAll('.kv-val-input');
            keyInputs.forEach((kEl, idx) => {
                const k = kEl.value.trim();
                if (k) headers[k] = valInputs[idx].value.trim();
            });

            let body = null;
            const bodyEl = document.getElementById('editBody');
            if (bodyEl && bodyEl.value.trim()) {
                try {
                    body = JSON.parse(bodyEl.value.trim());
                } catch(e) {
                    body = bodyEl.value;
                }
            }

            const resBox = document.getElementById('fullTabReplayResult');
            if (resBox) {
                resBox.style.display = 'block';
                resBox.innerHTML = '<div style="color: var(--primary); font-weight: 600; padding: 14px; background: #0f172a; border-radius: 8px;">⏳ Sending live request...</div>';
            }

            fetch('/api/replay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, method, headers, body })
            })
            .then(res => res.json())
            .then(data => {
                if (!resBox) return;
                if (data.error) {
                    resBox.innerHTML = `<div style="color: var(--danger); font-weight: 600; padding: 14px;">❌ Request Failed: ${escapeHtml(data.error)}</div>`;
                } else {
                    let badgeClass = data.status >= 200 && data.status < 400 ? 'badge-2xx' : 'badge-4xx';
                    let bodyTreeHtml = typeof data.body === 'object' ? buildJsonTreeHtml(data.body) : `<div class="json-str">${escapeHtml(data.body)}</div>`;
                    let bodyStr = typeof data.body === 'object' ? JSON.stringify(data.body, null, 2) : data.body;
                    
                    let headersRows = '';
                    if (data.headers) {
                        for (const [k, v] of Object.entries(data.headers)) {
                            headersRows += `<tr><td style="font-weight:600; color:var(--primary);">${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
                        }
                    }

                    resBox.innerHTML = `
                        <div style="background: var(--surface); border: 1px solid var(--primary); border-radius: 12px; padding: 20px; box-shadow: 0 0 20px rgba(56,189,248,0.2);">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; flex-wrap:wrap; gap:10px;">
                                <div style="display:flex; gap:12px; align-items:center;">
                                    <span class="badge ${badgeClass}">LIVE RESPONSE: Status ${data.status}</span>
                                    <span style="font-size:13px; color:var(--text-secondary);">Duration: <strong>${data.duration_ms} ms</strong></span>
                                </div>
                                <span style="font-size:12px; color:var(--primary); font-weight:700;">⚡ Executed Just Now</span>
                            </div>
                            <div class="tab-nav">
                                <button class="tab-btn tab-btn-rep active" onclick="switchTab('rep', 0)">🌳 Live JSON Tree</button>
                                <button class="tab-btn tab-btn-rep" onclick="switchTab('rep', 1)">📄 Live Raw Body</button>
                                <button class="tab-btn tab-btn-rep" onclick="switchTab('rep', 2)">📋 Live Headers</button>
                            </div>
                            <div class="tab-pane tab-pane-rep active">
                                <div class="json-tree-container">${bodyTreeHtml}</div>
                            </div>
                            <div class="tab-pane tab-pane-rep">
                                <div class="code-box">${escapeHtml(bodyStr)}</div>
                            </div>
                            <div class="tab-pane tab-pane-rep">
                                <table>
                                    <thead><tr><th>Header</th><th>Value</th></tr></thead>
                                    <tbody>${headersRows}</tbody>
                                </table>
                            </div>
                        </div>
                    `;
                }
            })
            .catch(err => {
                if (resBox) resBox.innerHTML = `<div style="color:var(--danger); padding:14px;">❌ Error: ${err.message}</div>`;
            });
        }

        function loadRequest() {
            const params = new URLSearchParams(window.location.search);
            const reqId = params.get('id');
            if (!reqId) {
                document.getElementById('inspectorContent').innerHTML = '<div style="color:var(--danger); font-weight:600; text-align:center; padding:40px;">No request ID specified in URL. Please specify ?id=1</div>';
                return;
            }

            fetch('/api/request?id=' + reqId)
            .then(res => res.json())
            .then(data => {
                if (data.error || !data.request) {
                    document.getElementById('inspectorContent').innerHTML = `<div style="color:var(--danger); font-weight:600; text-align:center; padding:40px;">❌ ${data.error || 'Request not found'}</div>`;
                    return;
                }
                const req = data.request;
                currentRequestData = req;

                document.getElementById('pageTitle').innerText = `#${req.id} ${req.method} ${req.url}`;

                let statusBadgeClass = req.response_status >= 200 && req.response_status < 300 ? 'badge-2xx' : (req.response_status >= 300 && req.response_status < 400 ? 'badge-3xx' : 'badge-4xx');

                let resTreeHtml = typeof req.response_body === 'object' ? buildJsonTreeHtml(req.response_body) : (req.response_body ? `<div class="json-str">${escapeHtml(req.response_body)}</div>` : '<div style="color:var(--text-secondary);">No Response Body</div>');
                let resBodyStr = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : (req.response_body || 'No Response Body');
                let reqBodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body, null, 2) : (req.request_body || '');
                let curlCmd = generateCurlCommand(req);

                let reqHeadersRows = '';
                if (req.request_headers) {
                    for (const [k, v] of Object.entries(req.request_headers)) {
                        reqHeadersRows += `<tr><td style="font-weight:600; color:var(--primary);">${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
                    }
                }

                let resHeadersRows = '';
                if (req.response_headers) {
                    for (const [k, v] of Object.entries(req.response_headers)) {
                        resHeadersRows += `<tr><td style="font-weight:600; color:var(--primary);">${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
                    }
                }

                const content = document.getElementById('inspectorContent');
                content.innerHTML = `
                    <div style="background: var(--surface); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                        <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
                            <span class="badge ${statusBadgeClass}">${req.response_status} ${escapeHtml(req.status_text || '')}</span>
                            <div><span style="color:var(--text-secondary);">Duration:</span> <strong>${req.duration_ms} ms</strong></div>
                            <div><span style="color:var(--text-secondary);">Latency:</span> <strong>${req.latency_ms} ms</strong></div>
                            <div><span style="color:var(--text-secondary);">Total Size:</span> <strong>${(req.total_bytes / 1024).toFixed(1)} KB</strong></div>
                            <div><span style="color:var(--text-secondary);">Host:</span> <strong>${escapeHtml(req.host)}</strong></div>
                        </div>
                    </div>

                    <div id="fullTabReplayResult" style="display:none;"></div>

                    <div style="background: var(--surface); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px;">
                        <div class="tab-nav">
                            <button class="tab-btn tab-btn-main active" onclick="switchTab('main', 0)">📡 Response Inspector</button>
                            <button class="tab-btn tab-btn-main" onclick="switchTab('main', 1)">📤 Request Inspector</button>
                            <button class="tab-btn tab-btn-main" onclick="switchTab('main', 2)">✏️ Edit & Do Request</button>
                        </div>

                        <div class="tab-pane tab-pane-main active">
                            <div class="tab-nav">
                                <button class="tab-btn tab-btn-res active" onclick="switchTab('res', 0)">🌳 Interactive JSON Tree</button>
                                <button class="tab-btn tab-btn-res" onclick="switchTab('res', 1)">📄 Raw Body</button>
                                <button class="tab-btn tab-btn-res" onclick="switchTab('res', 2)">📋 Response Headers</button>
                            </div>
                            <div class="tab-pane tab-pane-res active">
                                <div class="json-tree-container">${resTreeHtml}</div>
                            </div>
                            <div class="tab-pane tab-pane-res">
                                <div class="code-box">${escapeHtml(resBodyStr)}</div>
                            </div>
                            <div class="tab-pane tab-pane-res">
                                <table>
                                    <thead><tr><th>Header</th><th>Value</th></tr></thead>
                                    <tbody>${resHeadersRows}</tbody>
                                </table>
                            </div>
                        </div>

                        <div class="tab-pane tab-pane-main">
                            <div class="tab-nav">
                                <button class="tab-btn tab-btn-req active" onclick="switchTab('req', 0)">⚡ cURL Command</button>
                                <button class="tab-btn tab-btn-req" onclick="switchTab('req', 1)">📋 Request Headers</button>
                                <button class="tab-btn tab-btn-req" onclick="switchTab('req', 2)">📦 Payload Body</button>
                            </div>
                            <div class="tab-pane tab-pane-req active">
                                <div class="code-box">${escapeHtml(curlCmd)}</div>
                            </div>
                            <div class="tab-pane tab-pane-req">
                                <table>
                                    <thead><tr><th>Header</th><th>Value</th></tr></thead>
                                    <tbody>${reqHeadersRows}</tbody>
                                </table>
                            </div>
                            <div class="tab-pane tab-pane-req">
                                <div class="code-box">${escapeHtml(reqBodyStr || 'No Request Payload')}</div>
                            </div>
                        </div>

                        <div class="tab-pane tab-pane-main">
                            <div style="display:flex; flex-direction:column; gap:16px;">
                                <div style="display:flex; gap:12px; align-items:center;">
                                    <select id="editMethod" class="param-select" style="width:120px;">
                                        <option value="GET">GET</option>
                                        <option value="POST">POST</option>
                                        <option value="PUT">PUT</option>
                                        <option value="DELETE">DELETE</option>
                                        <option value="PATCH">PATCH</option>
                                        <option value="OPTIONS">OPTIONS</option>
                                    </select>
                                    <input type="text" id="editUrl" class="param-input" value="${escapeHtml(req.url)}" placeholder="Target URL">
                                    <button class="btn btn-primary" onclick="doReplayFromFullTab()">🔄 Do request</button>
                                </div>

                                <div>
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                        <strong style="font-size:13px; color:var(--primary);">Request Headers</strong>
                                        <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="addHeaderRow()">+ Add Header</button>
                                    </div>
                                    <div id="headersEditorContainer"></div>
                                </div>

                                <div>
                                    <strong style="font-size:13px; color:var(--primary); display:block; margin-bottom:6px;">Request Body (JSON or text)</strong>
                                    <textarea id="editBody" class="param-textarea" rows="6" placeholder="Request body payload...">${escapeHtml(reqBodyStr)}</textarea>
                                </div>
                            </div>
                        </div>
                    </div>
                `;

                document.getElementById('editMethod').value = req.method;

                if (req.request_headers) {
                    for (const [k, v] of Object.entries(req.request_headers)) {
                        addHeaderRow(k, String(v));
                    }
                }
            })
            .catch(err => {
                document.getElementById('inspectorContent').innerHTML = `<div style="color:var(--danger); font-weight:600; text-align:center; padding:40px;">❌ Error loading request: ${err.message}</div>`;
            });
        }

        window.onload = loadRequest;
    </script>
</body>
</html>"""

    def render_web_app_html(self) -> str:
        """Render frontend Web Application HTML/JS/CSS SPA."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Charles Proxy File Analyzer Web App</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --surface: #111827;
            --card-bg: #1f2937;
            --card-border: #374151;
            --card-hover: #2d3748;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.25);
            --accent: #a855f7;
            --text: #f9fafb;
            --text-secondary: #9ca3af;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --radius: 12px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* Header Navigation */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 16px 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }
        .logo-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 15px var(--primary-glow);
        }
        .logo-text h1 {
            font-size: 18px;
            font-weight: 700;
            background: linear-gradient(90deg, #38bdf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .logo-text p {
            font-size: 12px;
            color: var(--text-secondary);
        }
        .action-bar {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.2s ease;
            text-decoration: none;
        }
        .btn-primary {
            background: linear-gradient(135deg, #0284c7, #7e22ce);
            color: #fff;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
        }
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(2, 132, 199, 0.5);
        }
        .btn-secondary {
            background: var(--card-bg);
            border-color: var(--card-border);
            color: var(--text);
        }
        .btn-secondary:hover {
            background: var(--card-hover);
            border-color: var(--primary);
            color: var(--primary);
        }
        .btn-outline {
            background: transparent;
            border: 1px solid var(--card-border);
            color: var(--text-secondary);
        }
        .btn-outline:hover {
            border-color: var(--primary);
            color: var(--primary);
        }

        /* Upload Zone (Compact & Hideable) */
        .upload-section {
            background: var(--surface);
            border: 2px dashed var(--card-border);
            border-radius: var(--radius);
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 16px;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .upload-section:hover, .upload-section.dragover {
            border-color: var(--primary);
            background: rgba(56, 189, 248, 0.05);
            box-shadow: 0 0 20px var(--primary-glow);
        }
        .upload-icon {
            font-size: 28px;
            color: var(--primary);
        }
        .upload-title {
            font-size: 14px;
            font-weight: 600;
        }
        .upload-desc {
            font-size: 12px;
            color: var(--text-secondary);
        }
        .file-input { display: none; }
        .hidden { display: none !important; }

        /* Metrics KPI Grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }
        .kpi-card {
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
            overflow: hidden;
        }
        .kpi-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .kpi-value {
            font-size: 26px;
            font-weight: 800;
            color: var(--text);
        }
        .kpi-sub {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* Analytics Section */
        .analytics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) { .analytics-grid { grid-template-columns: 1fr; } }
        .panel {
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 12px;
        }
        .panel-title {
            font-size: 15px;
            font-weight: 700;
            color: var(--primary);
        }

        .bar-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 12px;
        }
        .bar-label {
            display: flex;
            justify-content: space-between;
            color: var(--text);
            font-weight: 500;
        }
        .bar-track {
            height: 8px;
            background: var(--card-bg);
            border-radius: 4px;
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            border-radius: 4px;
            background: linear-gradient(90deg, var(--primary), var(--accent));
            transition: width 0.5s ease;
        }

        /* Controls & Search */
        .controls-row {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
        }
        .search-input {
            flex: 1;
            min-width: 280px;
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 10px 16px;
            color: #fff;
            font-size: 14px;
            outline: none;
        }
        .search-input:focus { border-color: var(--primary); }

        .filter-chip {
            background: var(--surface);
            border: 1px solid var(--card-border);
            color: var(--text-secondary);
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .filter-chip.active, .filter-chip:hover {
            background: var(--primary);
            color: #000;
            border-color: var(--primary);
        }

        /* Data Table */
        .table-wrapper {
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 13px;
        }
        th {
            background: #161e2e;
            padding: 14px 18px;
            color: var(--text-secondary);
            font-weight: 600;
            border-bottom: 1px solid var(--card-border);
            cursor: pointer;
            user-select: none;
        }
        th:hover { color: var(--text); }
        td {
            padding: 12px 18px;
            border-bottom: 1px solid var(--card-border);
            word-break: break-all;
        }
        tr:hover { background: var(--card-bg); cursor: pointer; }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
        }
        .badge-2xx { background: rgba(52, 211, 153, 0.2); color: var(--success); }
        .badge-3xx { background: rgba(251, 191, 36, 0.2); color: var(--warning); }
        .badge-4xx, .badge-5xx, .badge-err { background: rgba(248, 113, 113, 0.2); color: var(--danger); }
        .badge-method { background: var(--card-bg); border: 1px solid var(--card-border); color: var(--text-secondary); }

        /* Structure View Tree Styles */
        .structure-container {
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 20px;
            font-size: 13px;
        }
        .tree-folder {
            margin-left: 12px;
            border-left: 1px dashed var(--card-border);
            padding-left: 8px;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        .tree-folder-header {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            user-select: none;
        }
        .tree-folder-header:hover { background: var(--card-bg); }
        .tree-folder-title { font-weight: 600; color: var(--text); }
        .tree-leaf {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            margin: 4px 0 4px 16px;
            background: var(--bg);
            border: 1px solid var(--card-border);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .tree-leaf:hover { border-color: var(--primary); background: var(--card-hover); }

        /* Modal Drawer */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            z-index: 100;
            align-items: center;
            justify-content: center;
        }
        .modal-container {
            background: var(--surface);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            width: 90%;
            max-width: 950px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
        }
        .modal-header {
            padding: 20px 24px;
            background: #161e2e;
            border-bottom: 1px solid var(--card-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-title { font-size: 16px; font-weight: 700; color: var(--primary); }
        .modal-close {
            background: none; border: none; color: var(--text-secondary);
            font-size: 24px; cursor: pointer;
        }
        .modal-close:hover { color: var(--text); }
        .modal-body {
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .code-box {
            background: var(--bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #e5e7eb;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 350px;
            overflow-y: auto;
        }

        /* Response Inspector Tabs & JSON Tree */
        .tab-nav {
            display: flex;
            gap: 4px;
            border-bottom: 1px solid var(--card-border);
            margin-bottom: 12px;
        }
        .tab-btn {
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            cursor: pointer;
        }
        .tab-btn.active {
            color: var(--primary);
            border-bottom-color: var(--primary);
        }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }

        .json-tree-container {
            background: var(--bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            max-height: 350px;
            overflow-y: auto;
        }
        .json-tree-bar {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 10px;
            align-items: center;
        }
        .json-search-input {
            background: var(--bg);
            border: 1px solid var(--card-border);
            border-radius: 6px;
            padding: 4px 10px;
            color: #fff;
            font-size: 11px;
            width: 220px;
        }

        .json-item { margin-left: 14px; }
        .json-key { color: #38bdf8; font-weight: 600; }
        .json-str { color: #34d399; }
        .json-num { color: #f63665; }
        .json-bool { color: #c084fc; font-weight: 700; }
        .json-null { color: #9ca3af; font-style: italic; }
        .json-toggle { cursor: pointer; user-select: none; color: #94a3b8; font-weight: 700; margin-right: 4px; }

        .param-input, .param-select, .param-textarea { background: var(--bg); border: 1px solid var(--card-border); border-radius: 6px; padding: 8px 12px; color: #fff; font-size: 13px; font-family: inherit; width: 100%; }
        .param-input:focus, .param-select:focus, .param-textarea:focus { border-color: var(--primary); outline: none; }
        .kv-row { display: flex; gap: 8px; margin-bottom: 8px; }

        /* Toast notification */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #0284c7;
            color: #fff;
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            display: none;
            z-index: 200;
        }
    </style>
</head>
<body>

    <!-- Header Navigation -->
    <header>
        <div class="logo-group">
            <div class="logo-icon">🚀</div>
            <div class="logo-text">
                <h1>Charles Proxy File Analyzer</h1>
                <p>Interactive Session Inspector & Debugger</p>
            </div>
        </div>
        <div class="action-bar">
            <button class="btn btn-outline" onclick="document.getElementById('fileInput').click()">📁 Attach .chlz File</button>
            <button class="btn btn-primary" onclick="loadExampleData()">⚡ Load example_1.chlz</button>
        </div>
    </header>

    <!-- Upload Zone (Compact & Hides on Selection) -->
    <div class="upload-section" id="dropZone" onclick="document.getElementById('fileInput').click()">
        <div class="upload-icon">📁</div>
        <div style="text-align: left;">
            <div class="upload-title">Drop your Charles session file (.chlz) here</div>
            <div class="upload-desc">or click to browse files from your computer</div>
        </div>
        <input type="file" id="fileInput" class="file-input" accept=".chlz">
    </div>

    <!-- Main Content Dashboard -->
    <main id="dashboardContent" class="hidden" style="display: flex; flex-direction: column; gap: 24px;">

        <!-- Export Action Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; background: var(--surface); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 14px 20px; flex-wrap: wrap; gap: 12px;">
            <div style="font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 8px;">
                <span>Session File:</span>
                <strong id="sessionFileName" style="color: var(--primary);">session.chlz</strong>
            </div>
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-secondary" onclick="exportHtmlReport()">📄 Download HTML Report</button>
                <button class="btn btn-secondary" onclick="exportJson()">💾 Export JSON</button>
                <button class="btn btn-secondary" onclick="exportCsv()">📊 Export CSV</button>
            </div>
        </div>

        <!-- Metrics KPI Grid -->
        <div class="metrics-grid">
            <div class="kpi-card">
                <div class="kpi-title">Total Requests</div>
                <div class="kpi-value" id="kpiTotalReqs">0</div>
                <div class="kpi-sub" id="kpiOkFail">0 Successful / 0 Failed</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Bandwidth Transfer</div>
                <div class="kpi-value" id="kpiBandwidth">0 MB</div>
                <div class="kpi-sub" id="kpiSentRecv">Sent: 0 KB | Recv: 0 MB</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Avg Latency / Response Time</div>
                <div class="kpi-value" id="kpiAvgDuration">0 ms</div>
                <div class="kpi-sub" id="kpiMinMax">Min: 0 ms | Max: 0 ms</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Unique Domains / Hosts</div>
                <div class="kpi-value" id="kpiUniqueHosts">0</div>
                <div class="kpi-sub">Target Hosts Inspected</div>
            </div>
        </div>

        <!-- Analytics Charts Grid -->
        <div class="analytics-grid">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">🌐 Top Target Hosts</div>
                </div>
                <div id="hostsBarChart" style="display: flex; flex-direction: column; gap: 10px;"></div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">📊 HTTP Status Code Breakdown</div>
                </div>
                <div id="statusCodesBarChart" style="display: flex; flex-direction: column; gap: 10px;"></div>
            </div>
        </div>

        <!-- Toolbar View Mode & Filtering Controls -->
        <div style="background: var(--surface); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 18px; display: flex; flex-direction: column; gap: 14px;">
            
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div style="display: flex; gap: 8px; align-items: center;">
                    <span style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-right: 4px;">View Mode:</span>
                    <button class="btn btn-primary" id="btnViewSequence" onclick="switchMainView('sequence')">📋 Sequence View</button>
                    <button class="btn btn-secondary" id="btnViewStructure" onclick="switchMainView('structure')">📂 Structure View</button>
                </div>
                
                <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                    <div class="filter-chip active" onclick="applyStatusFilter('all', this)">All Requests</div>
                    <div class="filter-chip" onclick="applyStatusFilter('2xx', this)">2xx Success</div>
                    <div class="filter-chip" onclick="applyStatusFilter('3xx', this)">3xx Redirect</div>
                    <div class="filter-chip" onclick="applyStatusFilter('4xx', this)">4xx Client Error</div>
                    <div class="filter-chip" onclick="applyStatusFilter('5xx', this)">5xx Server Error</div>
                </div>
            </div>

            <div class="controls-row">
                <input type="text" class="search-input" id="tableSearch" placeholder="🔍 Search by URL, host, path, status, or keyword..." oninput="onSearchInput()">
            </div>
        </div>

        <!-- Sequence View (Flat Table) -->
        <div class="table-wrapper" id="sequenceViewBox">
            <table>
                <thead>
                    <tr>
                        <th onclick="sortTable('id')">#</th>
                        <th onclick="sortTable('method')">Method</th>
                        <th onclick="sortTable('response_status')">Status</th>
                        <th onclick="sortTable('host')">Host</th>
                        <th onclick="sortTable('path')">Path</th>
                        <th onclick="sortTable('duration_ms')">Duration</th>
                        <th onclick="sortTable('total_bytes')">Size</th>
                    </tr>
                </thead>
                <tbody id="requestsTableBody"></tbody>
            </table>
        </div>

        <!-- Structure View (Grouped Folders) -->
        <div class="structure-container hidden" id="structureViewBox">
            <div id="structureTreeContent"></div>
        </div>

    </main>

    <!-- Modal Inspector Overlay -->
    <div class="modal-overlay" id="inspectorModal">
        <div class="modal-container">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle">Request Inspector</div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
        </div>
    </div>

    <div class="toast" id="toastMessage">Notification</div>

    <script>
        let currentSessionData = null;
        let activeRequestsList = [];
        let currentStatusFilter = 'all';
        let currentSearchQuery = '';
        let sortField = 'id';
        let sortAsc = true;
        let currentMainView = 'sequence';
        let currentModalReqId = null;

        // Initialize drag & drop and file input
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleFileSelect(e.target.files[0]);
            }
        });

        function showToast(msg) {
            const t = document.getElementById('toastMessage');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 2500);
        }

        function handleFileSelect(file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const base64Data = e.target.result.split(',')[1];
                uploadChlzFile(file.name, base64Data);
            };
            reader.readAsDataURL(file);
        }

        function uploadChlzFile(filename, fileB64) {
            fetch('/api/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename, file_b64: fileB64 })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert('Error: ' + data.error);
                } else {
                    loadSessionData(data);
                    showToast('Loaded ' + filename + ' successfully!');
                }
            })
            .catch(err => alert('Upload failed: ' + err.message));
        }

        function loadExampleData() {
            fetch('/api/example', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert('Error: ' + data.error);
                } else {
                    loadSessionData(data);
                    showToast('Loaded example_1.chlz!');
                }
            })
            .catch(err => alert('Failed to load example file: ' + err.message));
        }

        function loadSessionData(data) {
            currentSessionData = data;
            activeRequestsList = [...data.requests];

            document.getElementById('sessionFileName').innerText = data.filename || 'session.chlz';
            
            // Hide drop file zone on file selection
            document.getElementById('dropZone').classList.add('hidden');
            
            document.getElementById('dashboardContent').classList.remove('hidden');

            renderKPIs(data.summary);
            renderCharts(data.summary);
            applyFiltersAndRender();
        }

        function renderKPIs(s) {
            document.getElementById('kpiTotalReqs').innerText = s.total_requests;
            document.getElementById('kpiOkFail').innerText = `${s.successful_requests} Successful / ${s.failed_requests} Failed`;
            
            const mbTotal = (s.total_bytes / (1024 * 1024)).toFixed(2) + ' MB';
            const kbSent = (s.total_bytes_sent / 1024).toFixed(1) + ' KB';
            const mbRecv = (s.total_bytes_received / (1024 * 1024)).toFixed(2) + ' MB';
            document.getElementById('kpiBandwidth').innerText = mbTotal;
            document.getElementById('kpiSentRecv').innerText = `Sent: ${kbSent} | Recv: ${mbRecv}`;

            document.getElementById('kpiAvgDuration').innerText = s.avg_duration_ms + ' ms';
            document.getElementById('kpiMinMax').innerText = `Min: ${s.min_duration_ms} ms | Max: ${s.max_duration_ms} ms`;

            document.getElementById('kpiUniqueHosts').innerText = Object.keys(s.hosts).length;
        }

        function renderCharts(s) {
            // Hosts bar chart
            const hostsBox = document.getElementById('hostsBarChart');
            hostsBox.innerHTML = '';
            const topHosts = Object.entries(s.hosts).slice(0, 5);
            const maxHostCount = topHosts.length ? topHosts[0][1] : 1;

            topHosts.forEach(([host, count]) => {
                const pct = Math.round((count / maxHostCount) * 100);
                hostsBox.innerHTML += `
                    <div class="bar-item">
                        <div class="bar-label"><span>${host}</span><span>${count} reqs</span></div>
                        <div class="bar-track"><div class="bar-fill" style="width: ${pct}%;"></div></div>
                    </div>
                `;
            });

            // Status Codes bar chart
            const statusBox = document.getElementById('statusCodesBarChart');
            statusBox.innerHTML = '';
            const statusEntries = Object.entries(s.status_codes);
            const maxStatusCount = Math.max(...statusEntries.map(e => e[1]), 1);

            statusEntries.forEach(([code, count]) => {
                const pct = Math.round((count / maxStatusCount) * 100);
                statusBox.innerHTML += `
                    <div class="bar-item">
                        <div class="bar-label"><span>Status Code ${code}</span><span>${count} reqs</span></div>
                        <div class="bar-track"><div class="bar-fill" style="width: ${pct}%;"></div></div>
                    </div>
                `;
            });
        }

        function switchMainView(mode) {
            currentMainView = mode;
            document.getElementById('btnViewSequence').className = mode === 'sequence' ? 'btn btn-primary' : 'btn btn-secondary';
            document.getElementById('btnViewStructure').className = mode === 'structure' ? 'btn btn-primary' : 'btn btn-secondary';

            document.getElementById('sequenceViewBox').classList.toggle('hidden', mode !== 'sequence');
            document.getElementById('structureViewBox').classList.toggle('hidden', mode !== 'structure');

            applyFiltersAndRender();
        }

        function applyStatusFilter(filter, el) {
            currentStatusFilter = filter;
            document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            applyFiltersAndRender();
        }

        function onSearchInput() {
            currentSearchQuery = document.getElementById('tableSearch').value.toLowerCase().trim();
            applyFiltersAndRender();
        }

        function applyFiltersAndRender() {
            if (!currentSessionData) return;

            activeRequestsList = currentSessionData.requests.filter(req => {
                // Status Filter
                if (currentStatusFilter === '2xx' && (req.response_status < 200 || req.response_status >= 300)) return false;
                if (currentStatusFilter === '3xx' && (req.response_status < 300 || req.response_status >= 400)) return false;
                if (currentStatusFilter === '4xx' && (req.response_status < 400 || req.response_status >= 500)) return false;
                if (currentStatusFilter === '5xx' && req.response_status < 500) return false;

                // Search Query
                if (currentSearchQuery) {
                    const matchUrl = req.url && req.url.toLowerCase().includes(currentSearchQuery);
                    const matchHost = req.host && req.host.toLowerCase().includes(currentSearchQuery);
                    const matchPath = req.path && req.path.toLowerCase().includes(currentSearchQuery);
                    const matchStatus = String(req.response_status).includes(currentSearchQuery);
                    return matchUrl || matchHost || matchPath || matchStatus;
                }

                return true;
            });

            // Sorting
            activeRequestsList.sort((a, b) => {
                let valA = a[sortField];
                let valB = b[sortField];
                if (valA === undefined) valA = '';
                if (valB === undefined) valB = '';
                if (typeof valA === 'string') valA = valA.toLowerCase();
                if (typeof valB === 'string') valB = valB.toLowerCase();
                if (valA < valB) return sortAsc ? -1 : 1;
                if (valA > valB) return sortAsc ? 1 : -1;
                return 0;
            });

            if (currentMainView === 'sequence') {
                renderTable();
            } else {
                renderStructureView();
            }
        }

        function sortTable(field) {
            if (sortField === field) {
                sortAsc = !sortAsc;
            } else {
                sortField = field;
                sortAsc = true;
            }
            applyFiltersAndRender();
        }

        function renderTable() {
            const tbody = document.getElementById('requestsTableBody');
            tbody.innerHTML = '';

            if (activeRequestsList.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 30px;">No requests match current filter.</td></tr>';
                return;
            }

            activeRequestsList.forEach(req => {
                const tr = document.createElement('tr');
                tr.onclick = () => openInspector(req.id);
                
                let badgeClass = 'badge-2xx';
                if (req.response_status >= 300 && req.response_status < 400) badgeClass = 'badge-3xx';
                if (req.is_error || req.response_status >= 400) badgeClass = 'badge-4xx';

                const kbSize = (req.total_bytes / 1024).toFixed(1) + ' KB';

                tr.innerHTML = `
                    <td style="font-weight: 700; color: var(--primary);">${req.id}</td>
                    <td><span class="badge badge-method">${req.method}</span></td>
                    <td><span class="badge ${badgeClass}">${req.response_status || 'ERR'}</span></td>
                    <td>${escapeHtml(req.host)}</td>
                    <td>${escapeHtml(req.path)}</td>
                    <td>${req.duration_ms} ms</td>
                    <td>${kbSize}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function renderStructureView() {
            const container = document.getElementById('structureTreeContent');
            container.innerHTML = '';

            if (activeRequestsList.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 30px;">No requests match current filter.</div>';
                return;
            }

            // Build Host -> Path Directory Tree
            const tree = {};

            activeRequestsList.forEach(req => {
                const host = req.host || 'other-hosts';
                if (!tree[host]) tree[host] = [];
                tree[host].push(req);
            });

            let html = '';
            for (const [host, reqs] of Object.entries(tree)) {
                html += `
                    <div class="tree-folder">
                        <div class="tree-folder-header" onclick="toggleTreeFolder(this)">
                            <span class="json-toggle">▼</span>
                            <span style="font-size:16px;">🌐</span>
                            <span class="tree-folder-title">${escapeHtml(host)}</span>
                            <span class="badge badge-method" style="margin-left:auto;">${reqs.length} requests</span>
                        </div>
                        <div class="tree-node-children">
                `;

                reqs.forEach(req => {
                    let badgeClass = req.response_status >= 200 && req.response_status < 300 ? 'badge-2xx' : (req.response_status >= 300 && req.response_status < 400 ? 'badge-3xx' : 'badge-4xx');
                    html += `
                        <div class="tree-leaf" onclick="openInspector(${req.id})">
                            <div style="display:flex; align-items:center; gap:10px; overflow:hidden;">
                                <span class="badge badge-method">${req.method}</span>
                                <span class="badge ${badgeClass}">${req.response_status}</span>
                                <span style="font-weight:600; color:var(--text); word-break:break-all;">${escapeHtml(req.path)}</span>
                            </div>
                            <div style="display:flex; gap:12px; align-items:center; font-size:11px; color:var(--text-secondary);">
                                <span>#${req.id}</span>
                                <span>${req.duration_ms} ms</span>
                            </div>
                        </div>
                    `;
                });

                html += `</div></div>`;
            }

            container.innerHTML = html;
        }

        function toggleTreeFolder(headerEl) {
            const children = headerEl.nextElementSibling;
            const toggle = headerEl.querySelector('.json-toggle');
            if (children.style.display === 'none') {
                children.style.display = 'block';
                toggle.innerText = '▼';
            } else {
                children.style.display = 'none';
                toggle.innerText = '▶';
            }
        }

        function generateCurlCommand(req) {
            let cmd = `curl -X ${req.method} "${req.url}"`;
            if (req.request_headers) {
                for (const [k, v] of Object.entries(req.request_headers)) {
                    cmd += ` \\\n  -H "${k}: ${String(v).replace(/"/g, '\\"')}"`;
                }
            }
            if (req.request_body) {
                let bodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body) : String(req.request_body);
                cmd += ` \\\n  --data '${bodyStr.replace(/'/g, "'\\''")}'`;
            }
            return cmd;
        }

        function copyCurl(reqId) {
            const req = currentSessionData.requests.find(r => r.id === reqId);
            if (!req) return;
            const curlCmd = generateCurlCommand(req);
            navigator.clipboard.writeText(curlCmd).then(() => showToast('Copied cURL command to clipboard! 📋'));
        }

        function openFullTabInspector(reqId) {
            window.open('/inspector.html?id=' + reqId, '_blank');
        }

        function addModalHeaderRow(key = '', val = '') {
            const container = document.getElementById('modalHeadersEditorContainer');
            if (!container) return;
            const row = document.createElement('div');
            row.className = 'kv-row';
            row.innerHTML = `
                <input type="text" class="param-input m-kv-key" placeholder="Header Name" value="${escapeHtml(key)}">
                <input type="text" class="param-input m-kv-val" placeholder="Header Value" value="${escapeHtml(val)}">
                <button type="button" class="btn btn-secondary" style="padding: 4px 10px;" onclick="this.parentElement.remove()">🗑️</button>
            `;
            container.appendChild(row);
        }

        function executeModalDoRequest(reqId) {
            const method = document.getElementById('modalEditMethod') ? document.getElementById('modalEditMethod').value : 'GET';
            const url = document.getElementById('modalEditUrl') ? document.getElementById('modalEditUrl').value : '';

            const headers = {};
            const keys = document.querySelectorAll('.m-kv-key');
            const vals = document.querySelectorAll('.m-kv-val');
            keys.forEach((kEl, idx) => {
                const k = kEl.value.trim();
                if (k) headers[k] = vals[idx].value.trim();
            });

            let body = null;
            const bodyEl = document.getElementById('modalEditBody');
            if (bodyEl && bodyEl.value.trim()) {
                try {
                    body = JSON.parse(bodyEl.value.trim());
                } catch(e) {
                    body = bodyEl.value;
                }
            }

            const box = document.getElementById('replayResultBox');
            box.classList.remove('hidden');
            box.innerHTML = '<div style="color: var(--primary); font-weight: 600; padding: 12px; background: #0f172a; border-radius: 8px;">⏳ Sending live request...</div>';

            fetch('/api/replay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, method, headers, body })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    box.innerHTML = `<div style="color: var(--danger); font-weight: 600; padding: 12px;">❌ Replay Failed: ${escapeHtml(data.error)}</div>`;
                } else {
                    let badgeClass = data.status >= 200 && data.status < 400 ? 'badge-2xx' : 'badge-4xx';
                    let bodyStr = typeof data.body === 'object' ? JSON.stringify(data.body, null, 2) : data.body;
                    let treeHtml = typeof data.body === 'object' ? buildJsonTreeHtml(data.body) : `<div class="json-str">${escapeHtml(data.body)}</div>`;
                    let headersHtml = renderHeadersTable(data.headers);

                    box.innerHTML = `
                        <div style="background: var(--surface); border: 1px solid var(--primary); border-radius: 10px; padding: 16px; margin-bottom: 15px; box-shadow: 0 0 15px rgba(56, 189, 248, 0.15);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px;">
                                <div style="display: flex; gap: 12px; align-items: center;">
                                    <span class="badge ${badgeClass}">LIVE RESPONSE: Status ${data.status}</span>
                                    <span style="font-size: 12px; color: var(--text-secondary);">Duration: <strong>${data.duration_ms} ms</strong></span>
                                </div>
                                <span style="font-size: 11px; color: var(--primary); font-weight: 600;">⚡ Executed Just Now</span>
                            </div>

                            <div class="tab-nav">
                                <button class="tab-btn tab-btn-replay active" onclick="switchTab('replay', 0)">🌳 Live JSON Tree</button>
                                <button class="tab-btn tab-btn-replay" onclick="switchTab('replay', 1)">📄 Live Raw Body</button>
                                <button class="tab-btn tab-btn-replay" onclick="switchTab('replay', 2)">📋 Live Headers</button>
                            </div>

                            <div class="tab-pane tab-pane-replay active">
                                <div id="replayTreeBox" class="json-tree-container">${treeHtml}</div>
                            </div>

                            <div class="tab-pane tab-pane-replay">
                                <div class="code-box">${escapeHtml(bodyStr)}</div>
                            </div>

                            <div class="tab-pane tab-pane-replay">
                                ${headersHtml}
                            </div>
                        </div>
                    `;
                }
            })
            .catch(err => {
                box.innerHTML = `<div style="color: var(--danger); font-weight: 600; padding: 12px;">❌ Replay Error: ${err.message}</div>`;
            });
        }

        function openInspector(reqId) {
            const req = currentSessionData.requests.find(r => r.id === reqId);
            if (!req) return;
            currentModalReqId = reqId;

            document.getElementById('modalTitle').innerText = `#${req.id} ${req.method} ${req.url}`;
            const modalBody = document.getElementById('modalBody');

            let reqBodyStr = typeof req.request_body === 'object' ? JSON.stringify(req.request_body, null, 2) : (req.request_body || '');
            let resBodyStr = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : (req.response_body || 'No Response Body');
            let curlCmd = generateCurlCommand(req);

            let resTreeHtml = typeof req.response_body === 'object' ? buildJsonTreeHtml(req.response_body) : (req.response_body ? `<div class="json-str">${escapeHtml(req.response_body)}</div>` : '<div style="color:var(--text-secondary);">No Response Body</div>');
            let reqTreeHtml = typeof req.request_body === 'object' ? buildJsonTreeHtml(req.request_body) : (req.request_body ? `<div class="json-str">${escapeHtml(req.request_body)}</div>` : '<div style="color:var(--text-secondary);">No Request Body</div>');

            let resHeadersHtml = renderHeadersTable(req.response_headers);
            let reqHeadersHtml = renderHeadersTable(req.request_headers);

            let statusBadgeClass = req.response_status >= 200 && req.response_status < 300 ? 'badge-2xx' : (req.response_status >= 300 && req.response_status < 400 ? 'badge-3xx' : 'badge-4xx');

            modalBody.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; background: #161e2e; padding: 14px 18px; border-radius: 10px; flex-wrap: wrap; gap: 12px; border: 1px solid var(--card-border);">
                    <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap; font-size: 13px;">
                        <span class="badge ${statusBadgeClass}">${req.response_status} ${escapeHtml(req.status_text || '')}</span>
                        <div><span style="color:var(--text-secondary);">Time:</span> <strong>${req.duration_ms} ms</strong></div>
                        <div><span style="color:var(--text-secondary);">Latency:</span> <strong>${req.latency_ms} ms</strong></div>
                        <div><span style="color:var(--text-secondary);">Total Size:</span> <strong>${(req.total_bytes / 1024).toFixed(1)} KB</strong></div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-primary" onclick="executeModalDoRequest(${req.id})">🔄 Do request</button>
                        <button class="btn btn-outline" onclick="openFullTabInspector(${req.id})">↗️ Open in Full Tab</button>
                        <button class="btn btn-secondary" onclick="copyCurl(${req.id})">📋 Copy cURL</button>
                        <button class="btn btn-secondary" onclick="downloadResponseBody(${req.id})">💾 Download</button>
                    </div>
                </div>

                <div id="replayResultBox" class="hidden"></div>

                <div style="background: var(--surface); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px;">
                    <div class="tab-nav">
                        <button class="tab-btn tab-btn-res active" onclick="switchTab('res', 0)">🌳 Interactive Response JSON</button>
                        <button class="tab-btn tab-btn-res" onclick="switchTab('res', 1)">📄 Raw Response Body</button>
                        <button class="tab-btn tab-btn-res" onclick="switchTab('res', 2)">📋 Response Headers</button>
                    </div>

                    <div class="tab-pane tab-pane-res active">
                        <div class="json-tree-bar">
                            <input type="text" class="json-search-input" placeholder="🔍 Search JSON..." oninput="filterJsonTree(this.value, 'resTreeBox')">
                            <div style="display: flex; gap: 6px;">
                                <button class="btn btn-secondary" style="padding: 2px 8px; font-size: 10px;" onclick="expandAllJson('resTreeBox')">Expand</button>
                                <button class="btn btn-secondary" style="padding: 2px 8px; font-size: 10px;" onclick="collapseAllJson('resTreeBox')">Collapse</button>
                            </div>
                        </div>
                        <div id="resTreeBox" class="json-tree-container">${resTreeHtml}</div>
                    </div>

                    <div class="tab-pane tab-pane-res">
                        <div class="code-box">${escapeHtml(resBodyStr)}</div>
                    </div>

                    <div class="tab-pane tab-pane-res">
                        ${resHeadersHtml}
                    </div>
                </div>

                <div style="background: var(--surface); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px;">
                    <h3 style="color: var(--primary); font-size: 14px; font-weight: 700; margin-bottom: 12px;">📤 Request Parameters & Payload</h3>

                    <div class="tab-nav">
                        <button class="tab-btn tab-btn-req active" onclick="switchTab('req', 0)">⚡ cURL Command</button>
                        <button class="tab-btn tab-btn-req" onclick="switchTab('req', 1)">📋 Request Headers</button>
                        <button class="tab-btn tab-btn-req" onclick="switchTab('req', 2)">📦 Payload Body</button>
                        <button class="tab-btn tab-btn-req" onclick="switchTab('req', 3)">✏️ Edit & Do Request</button>
                    </div>

                    <div class="tab-pane tab-pane-req active">
                        <div class="code-box">${escapeHtml(curlCmd)}</div>
                    </div>

                    <div class="tab-pane tab-pane-req">
                        ${reqHeadersHtml}
                    </div>

                    <div class="tab-pane tab-pane-req">
                        <div class="json-tree-container">${reqTreeHtml}</div>
                    </div>

                    <div class="tab-pane tab-pane-req">
                        <div style="display:flex; flex-direction:column; gap:14px;">
                            <div style="display:flex; gap:10px; align-items:center;">
                                <select id="modalEditMethod" class="param-select" style="width:110px;">
                                    <option value="GET">GET</option>
                                    <option value="POST">POST</option>
                                    <option value="PUT">PUT</option>
                                    <option value="DELETE">DELETE</option>
                                    <option value="PATCH">PATCH</option>
                                    <option value="OPTIONS">OPTIONS</option>
                                </select>
                                <input type="text" id="modalEditUrl" class="param-input" value="${escapeHtml(req.url)}" placeholder="Target URL">
                                <button class="btn btn-primary" onclick="executeModalDoRequest(${req.id})">🔄 Do request</button>
                            </div>

                            <div>
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                    <strong style="font-size:12px; color:var(--primary);">Request Headers Editor</strong>
                                    <button class="btn btn-secondary" style="padding:3px 8px; font-size:11px;" onclick="addModalHeaderRow()">+ Add Header</button>
                                </div>
                                <div id="modalHeadersEditorContainer"></div>
                            </div>

                            <div>
                                <strong style="font-size:12px; color:var(--primary); display:block; margin-bottom:6px;">Request Body Editor</strong>
                                <textarea id="modalEditBody" class="param-textarea" rows="5" placeholder="Request body payload...">${escapeHtml(reqBodyStr)}</textarea>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.getElementById('modalEditMethod').value = req.method;
            if (req.request_headers) {
                for (const [k, v] of Object.entries(req.request_headers)) {
                    addModalHeaderRow(k, String(v));
                }
            }

            document.getElementById('inspectorModal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('inspectorModal').style.display = 'none';
        }

        function renderHeadersTable(headersObj) {
            if (!headersObj || Object.keys(headersObj).length === 0) return '<div style="color:var(--text-secondary);">No Headers</div>';
            let rows = '';
            for (const [k, v] of Object.entries(headersObj)) {
                rows += `<tr><td style="font-weight:600; color:var(--primary);">${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
            }
            return `<table><thead><tr><th>Header Name</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
        }

        function buildJsonTreeHtml(obj) {
            if (obj === null) return '<span class="json-null">null</span>';
            if (typeof obj === 'number') return `<span class="json-num">${obj}</span>`;
            if (typeof obj === 'boolean') return `<span class="json-bool">${obj}</span>`;
            if (typeof obj === 'string') return `<span class="json-str">"${escapeHtml(obj)}"</span>`;

            const isArray = Array.isArray(obj);
            const keys = Object.keys(obj);
            if (keys.length === 0) return isArray ? '[]' : '{}';

            let html = `<span class="json-toggle" onclick="toggleJsonNode(this)">▼</span><span>${isArray ? '[' : '{'}</span><div class="json-node-content">`;
            keys.forEach((key, idx) => {
                const val = obj[key];
                const comma = idx < keys.length - 1 ? ',' : '';
                html += `<div class="json-item">`;
                if (!isArray) html += `<span class="json-key">"${escapeHtml(key)}"</span>: `;
                html += buildJsonTreeHtml(val) + comma + `</div>`;
            });
            html += `</div><span>${isArray ? ']' : '}'}</span>`;
            return html;
        }

        function toggleJsonNode(el) {
            const content = el.nextElementSibling.nextElementSibling;
            if (content.style.display === 'none') {
                content.style.display = 'block';
                el.innerText = '▼';
            } else {
                content.style.display = 'none';
                el.innerText = '▶';
            }
        }

        function filterJsonTree(query, containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;
            const q = query.toLowerCase().trim();
            const items = container.querySelectorAll('.json-item');

            items.forEach(item => {
                if (!q) {
                    item.style.display = 'block';
                } else {
                    const text = item.innerText.toLowerCase();
                    item.style.display = text.includes(q) ? 'block' : 'none';
                }
            });
        }

        function expandAllJson(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.querySelectorAll('.json-node-content').forEach(el => el.style.display = 'block');
            container.querySelectorAll('.json-toggle').forEach(el => el.innerText = '▼');
        }

        function collapseAllJson(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.querySelectorAll('.json-node-content').forEach(el => el.style.display = 'none');
            container.querySelectorAll('.json-toggle').forEach(el => el.innerText = '▶');
        }

        function switchTab(group, index) {
            const btns = document.querySelectorAll('.tab-btn-' + group);
            const panes = document.querySelectorAll('.tab-pane-' + group);
            btns.forEach((b, i) => b.classList.toggle('active', i === index));
            panes.forEach((p, i) => p.classList.toggle('active', i === index));
        }

        function copyResponseBody(reqId) {
            const req = currentSessionData.requests.find(r => r.id === reqId);
            if (!req || !req.response_body) return;
            let bodyStr = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : String(req.response_body);
            navigator.clipboard.writeText(bodyStr).then(() => showToast('Copied response body to clipboard! 📋'));
        }

        function downloadResponseBody(reqId) {
            const req = currentSessionData.requests.find(r => r.id === reqId);
            if (!req || !req.response_body) return;
            let bodyStr = typeof req.response_body === 'object' ? JSON.stringify(req.response_body, null, 2) : String(req.response_body);
            const blob = new Blob([bodyStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `response_${req.id}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('Downloaded response body file! 💾');
        }

        function exportHtmlReport() {
            window.open('/api/export/html', '_blank');
        }

        function exportJson() {
            window.open('/api/export/json', '_blank');
        }

        function exportCsv() {
            window.open('/api/export/csv', '_blank');
        }

        function escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        window.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        document.getElementById('inspectorModal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });

        // Load default example file on startup
        window.onload = function() {
            loadExampleData();
        };
    </script>
</body>
</html>"""


def start_server(port: int = 8000, open_browser: bool = True):
    """Start local web server on port."""
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, CharlesWebHandler)
    url = f"http://localhost:{port}"
    print("\n" + "=" * 70)
    print(f" 🌐 CHARLES PROXY WEB ANALYZER RUNNING AT: {url}")
    print("=" * 70)
    print(" Press Ctrl+C to stop server.\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        httpd.server_close()


def main():
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port=port, open_browser=True)


if __name__ == "__main__":
    main()
