"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python main.py` from the repo root without setting PYTHONPATH.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from crawler.config import DEFAULT_SQLITE_PATH
from crawler.metrics import MetricsMonitor
from crawler.storage import Database
from ui.cli import CliApplication
from ui.runtime import AppRuntime
from ui.web import WebApplication



def main() -> None:
    database = Database(DEFAULT_SQLITE_PATH)
    metrics = MetricsMonitor()
    runtime = AppRuntime(database, metrics)

    web = WebApplication(runtime, host="127.0.0.1", port=8080)
    web.start_background()
    print(f"Web UI: {web.base_url}/", flush=True)

    try:
        CliApplication(runtime=runtime, close_database_on_exit=False).run()
    finally:
        web.shutdown()
        runtime.database.close()


if __name__ == "__main__":
    main()
