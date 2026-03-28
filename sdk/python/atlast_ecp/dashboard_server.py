"""
ATLAST ECP Local Dashboard Server.

Serves a web UI on localhost for visual record exploration.
All data stays local — reads from ~/.ecp/ SQLite index.

Usage: atlast dashboard [--port 3827] [--no-open]
"""

import json
import os
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ASSETS_DIR = Path(__file__).parent / "dashboard_assets"
DEFAULT_PORT = 3827


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local dashboard."""

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path.startswith("/api/"):
            self._handle_api(path, params)
            return

        # Static files
        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif path.endswith(".js"):
            self._serve_file(path.lstrip("/"), "application/javascript")
        elif path.endswith(".css"):
            self._serve_file(path.lstrip("/"), "text/css")
        else:
            self._serve_file("index.html", "text/html")

    def _serve_file(self, filename: str, content_type: str):
        filepath = (ASSETS_DIR / filename).resolve()
        # Prevent path traversal — file must be under ASSETS_DIR
        if not str(filepath).startswith(str(ASSETS_DIR.resolve())):
            self.send_error(403, "Forbidden")
            return
        if not filepath.exists():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(filepath.read_bytes())

    def _handle_api(self, path: str, params: dict):
        try:
            result = self._dispatch_api(path, params)
            self._json_response(200, result)
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    def _dispatch_api(self, path: str, params: dict) -> dict:
        from .query import search, trace, audit, timeline, rebuild_index

        if path == "/api/search":
            query = params.get("q", [""])[0]
            limit = int(params.get("limit", ["20"])[0])
            errors_only = params.get("errors", [""])[0] == "1"
            agent = params.get("agent", [None])[0]
            since = params.get("since", [None])[0]
            until = params.get("until", [None])[0]
            results = search(query, limit=limit, agent=agent, since=since,
                             until=until, errors_only=errors_only, as_json=True)
            return {"results": results, "count": len(results)}

        elif path == "/api/trace":
            record_id = params.get("id", [""])[0]
            direction = params.get("dir", ["back"])[0]
            if not record_id:
                return {"error": "id parameter required"}
            chain = trace(record_id, direction=direction, as_json=True)
            return {"chain": chain, "depth": len(chain)}

        elif path == "/api/audit":
            days = int(params.get("days", ["30"])[0])
            agent = params.get("agent", [None])[0]
            return audit(days=days, agent=agent, as_json=True)

        elif path == "/api/timeline":
            days = int(params.get("days", ["30"])[0])
            agent = params.get("agent", [None])[0]
            results = timeline(days=days, agent=agent, as_json=True)
            return {"timeline": results}

        elif path == "/api/index":
            count = rebuild_index()
            return {"indexed": count}

        elif path == "/api/stats":
            from .storage import count_records
            from .identity import get_or_create_identity
            try:
                identity = get_or_create_identity()
                did = identity.get("did", "unknown")
            except Exception:
                did = "not initialized"
            return {
                "total_records": count_records(),
                "agent_did": did,
                "ecp_dir": str(os.environ.get("ECP_DIR", "~/.ecp")),
            }

        return {"error": f"Unknown API: {path}"}

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        # No CORS header — dashboard HTML is served from same origin (127.0.0.1)
        self.end_headers()
        self.wfile.write(body)


def start_dashboard(port: int = DEFAULT_PORT, open_browser: bool = True):
    """Start the local dashboard server."""
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    url = f"http://127.0.0.1:{port}"

    print(f"\n  📊 ATLAST ECP Dashboard")
    print(f"  Running at: {url}")
    print(f"  Data: ~/.ecp/ (local only, nothing leaves your machine)")
    print(f"  Press Ctrl+C to stop\n")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()
