"""Minimal Web UI using stdlib http.server + threading (PRD 6.3 visibility)."""

from __future__ import annotations

import json
import socketserver
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from crawler.search import SearchEngine

from .runtime import AppRuntime

# Single-page dashboard (no external assets; stdlib only).
_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SpiderEngine | AI Dashboard</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🕷️</text></svg>">
  <style>
    :root {
      --bg: #0d0208;
      --panel: #1a0a13;
      --card: #2d0f21;
      --text: #ffeef8;
      --muted: #a68ba0;
      --accent: #ff2e88; /* Canlı Pembe */
      --accent-glow: rgba(255, 46, 136, 0.3);
      --ok: #00ff9f;
      --warn: #ffcc00;
      --border: #4a1d35;
    }
    * { box-sizing: border-box; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
    body {
      font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      background-image: radial-gradient(circle at 50% -20%, #4a1d35 0%, var(--bg) 80%);
      color: var(--text);
      margin: 0; padding: 2rem; min-height: 100vh;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    h1 { 
      font-size: 2.2rem; font-weight: 800; margin: 0 0 0.5rem; 
      background: linear-gradient(90deg, var(--accent), #ff7eb3);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      display: flex; align-items: center; gap: 10px;
    }
    section {
      background: var(--panel);
      border-radius: 20px; padding: 1.5rem; margin-bottom: 2rem;
      border: 1px solid var(--border);
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); margin: 0 0 1.5rem; display: flex; align-items: center; gap: 8px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; }
    .metric {
      background: var(--card); border-radius: 15px; padding: 1.25rem;
      border: 1px solid transparent; position: relative; overflow: hidden;
    }
    .metric:hover { border-color: var(--accent); transform: translateY(-5px); box-shadow: 0 5px 15px var(--accent-glow); }
    .metric label { display: block; font-size: 0.7rem; color: var(--muted); margin-bottom: 0.5rem; font-weight: 600; }
    .metric span { font-size: 1.6rem; font-weight: 800; color: var(--accent); font-family: 'Courier New', monospace; }
    
    .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; }
    .idle { color: var(--ok); background: rgba(0, 255, 159, 0.1); }
    .throttled { color: var(--warn); background: rgba(255, 204, 0, 0.1); animation: blink 1.5s infinite; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

    .search-area { display: flex; gap: 10px; margin-bottom: 2rem; }
    input[type="search"] {
      flex: 1; background: #000; border: 1px solid var(--border);
      border-radius: 12px; padding: 1rem; color: #fff; font-size: 1rem;
    }
    input[type="search"]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
    button {
      background: var(--accent); color: white; border: none; padding: 0 2rem;
      border-radius: 12px; font-weight: 700; cursor: pointer; text-transform: uppercase;
    }
    button:hover { transform: scale(1.05); box-shadow: 0 0 20px var(--accent); }

    table { width: 100%; border-collapse: separate; border-spacing: 0 8px; margin-top: 1rem; }
    th { padding: 12px; text-align: left; color: var(--muted); font-size: 0.75rem; }
    td { 
      padding: 15px; background: rgba(255, 255, 255, 0.03); 
      border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
      animation: fadeIn 0.5s ease forwards;
    }
    td:first-child { border-left: 1px solid var(--border); border-radius: 12px 0 0 12px; color: var(--accent); font-weight: 600; }
    td:last-child { border-right: 1px solid var(--border); border-radius: 0 12px 12px 0; text-align: center; }
    tr:hover td { background: rgba(255, 46, 136, 0.05); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

    footer { text-align: center; margin-top: 3rem; color: var(--muted); font-size: 0.8rem; border-top: 1px solid var(--border); padding-top: 2rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1><span>🕷️</span> SpiderEngine</h1>
    <p style="color:var(--muted); margin-bottom: 2rem;">Multi-threaded Crawler & Search Interface v1.0</p>

    <section>
      <h2>📊 Live Statistics</h2>
      <div class="grid">
        <div class="metric"><label>Processed</label><span id="m-processed">0</span></div>
        <div class="metric"><label>Discovered</label><span id="m-discovered">0</span></div>
        <div class="metric"><label>Queue</label><span id="m-queue">0</span></div>
        <div class="metric"><label>Pending</label><span id="m-pending">0</span></div>
        <div class="metric"><label>Back-Pressure</label><span id="m-pressure" class="status-badge idle">IDLE</span></div>
        <div class="metric"><label>Status</label><span id="m-running" style="font-size: 1rem; text-transform: uppercase;">IDLE</span></div>
      </div>
      <p id="m-detail" style="color:var(--accent); font-size:0.8rem; margin-top:1rem; font-family:monospace;"></p>
    </section>

    <section>
      <h2>🔍 Search Engine</h2>
      <div class="search-area">
        <input type="search" id="q" placeholder="Type a keyword to search in indexed pages..." autocomplete="off" />
        <button type="button" id="btn-search">Search</button>
      </div>
      <div id="search-err" style="color:var(--accent); display:none; margin-bottom: 1rem;"></div>
      <table>
        <thead><tr><th>Target URL</th><th>Origin Source</th><th>Depth</th></tr></thead>
        <tbody id="results"></tbody>
      </table>
    </section>

    <footer>
      Powered by Python Standard Library &bull; SQLite3 WAL Mode &bull; Threaded HTTPServer
    </footer>
  </div>

  <script>
    async function refreshMetrics() {
      try {
        const r = await fetch('/api/metrics');
        const m = await r.json();
        if (!m.ok) return;
        document.getElementById('m-processed').textContent = m.processed_urls;
        document.getElementById('m-discovered').textContent = m.discovered_urls;
        document.getElementById('m-queue').textContent = m.queue_depth;
        document.getElementById('m-pending').textContent = m.pending_tasks;
        
        const p = document.getElementById('m-pressure');
        p.textContent = m.back_pressure;
        p.className = 'status-badge ' + (m.back_pressure === 'THROTTLED' ? 'throttled' : 'idle');
        
        const run = document.getElementById('m-running');
        run.textContent = m.crawl_running ? '⚡ Active' : '💤 Idle';
        run.style.color = m.crawl_running ? 'var(--ok)' : 'var(--muted)';
        
        document.getElementById('m-detail').textContent = m.throttle_detail ? '>> ' + m.throttle_detail : '';
      } catch (e) {}
    }

    async function doSearch() {
      const q = document.getElementById('q').value.trim();
      const tbody = document.getElementById('results');
      const err = document.getElementById('search-err');
      err.style.display = 'none';
      if (!q) return;

      try {
        const r = await fetch('/api/search?q=' + encodeURIComponent(q));
        const data = await r.json();
        tbody.innerHTML = '';
        if (data.results.length === 0) {
          tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:var(--muted)">No matching records found.</td></tr>';
          return;
        }
        data.results.forEach((row, index) => {
          const tr = document.createElement('tr');
          tr.style.animationDelay = (index * 0.05) + 's';
          
          const targetUrl = escapeHtml(row.relevant_url);
          const originUrl = escapeHtml(row.origin_url);
          
          tr.innerHTML = `
            <td>
              <a href="${targetUrl}" target="_blank" style="color:var(--accent); text-decoration:none; font-weight:600;">
                ${targetUrl} <span style="font-size:0.7rem;">↗</span>
              </a>
            </td>
            <td>
              <a href="${originUrl}" target="_blank" style="color:var(--muted); text-decoration:none; font-size:0.85rem;">
                ${originUrl}
              </a>
            </td>
            <td><span class="status-badge idle">${row.depth}</span></td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) { err.textContent = "Search error: " + e; err.style.display = 'block'; }
    }

    function escapeHtml(s) {
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }

    document.getElementById('btn-search').addEventListener('click', doSearch);
    document.getElementById('q').addEventListener('keydown', (e) => { if(e.key === 'Enter') doSearch(); });
    setInterval(refreshMetrics, 1000);
    refreshMetrics();
  </script>
</body>
</html>
"""


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Handle each request in a thread so the crawler is never blocked by HTTP I/O."""

    daemon_threads = True
    allow_reuse_address = True


def _make_handler_class(runtime: AppRuntime):
    class CrawlUIHandler(BaseHTTPRequestHandler):
        """Serve the dashboard HTML and JSON APIs."""

        runtime: AppRuntime  # set on class after definition

        def log_message(self, fmt: str, *args) -> None:
            return  # quiet default logging

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path in ("/", "/index.html"):
                self._send_html(_PAGE_HTML)
                return
            if path == "/api/metrics":
                self._send_json({"ok": True, **type(self).runtime.metrics_snapshot_dict()})
                return
            if path == "/api/search":
                qs = parse_qs(parsed.query or "")
                raw = (qs.get("q") or [""])[0]
                q = raw.strip()
                if not q:
                    self._send_json({"ok": False, "error": "Missing query parameter q"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    engine = SearchEngine(type(self).runtime.database)
                    hits = engine.search(q, limit=100)
                    results = [
                      {
                        "relevant_url": u,
                        "origin_url": o,
                        "depth": d,
                        "score": s
                      } for u, o, d, s in hits
                    ]
                    self._send_json({"ok": True, "results": results})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = html.encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self,
            data: dict,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    CrawlUIHandler.runtime = runtime
    return CrawlUIHandler


class WebApplication:
    """
    Runs :class:`ThreadingHTTPServer` on a background thread (default port 8080).

    Uses only the standard library. Search and metrics calls run in HTTP worker
    threads and do not block the crawler's own threads.
    """

    def __init__(
        self,
        runtime: AppRuntime,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        self._runtime = runtime
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start_background(self) -> None:
        """Start ``serve_forever`` on a daemon thread."""
        if self._server is not None:
            raise RuntimeError("Web server already started")
        handler = _make_handler_class(self._runtime)
        self._server = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="WebUIHTTPServer",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        """Stop the server (call from the main thread when exiting)."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def run(self) -> None:
        """Blocking serve (for testing); prefer :meth:`start_background` with CLI."""
        self.start_background()
        if self._thread:
            self._thread.join()
