
# Spider Engine: AI-Aided Web Crawler

## Project Motivation
This project aims to provide a robust, concurrent, and extensible web crawler and search engine using only Python’s standard library. It is designed for research, analytics, and educational use, enabling real-time search and monitoring while crawling is in progress. The system demonstrates best practices in concurrency, back-pressure, and safe persistence.

Product requirements: see [`product_prd.md`](product_prd.md).

## What’s implemented

| Area | Details |
|------|---------|
| Crawl | BFS from an origin URL, depth limit, `urllib.request` + `html.parser`, worker pool (`threading`), bounded queue back-pressure, global rate limit |
| Dedup | In-memory `VisitedRegistry` + optional resume from DB |
| Storage | `sqlite3` with **WAL**, `documents` (url, text, origin_url, depth) and `crawl_visited` |
| Search | Case-insensitive `LIKE` on content and URL; results are ranked by a custom relevancy score (see `crawler/search/relevancy.py`). Returns `(relevant_url, origin_url, depth, score)` in API and CLI. |
| UI | Interactive **CLI** with live `[metrics]` ticker. Modern **Web UI** (see below) with real-time dashboard, search, and metrics. |
| Metrics | `MetricsMonitor` — processed count, queue depth, discovered count, `IDLE` / `THROTTLED` |


## Installation

1. Ensure **Python 3.10+** is installed.
2. Clone this repository and navigate to the `spiderengine/` directory.
3. **Strictly Standard Library Only** The core engine, crawler, and web dashboard are built using only Python's built-in modules (urllib, sqlite3, http.server, etc.). No external dependencies like requests, BeautifulSoup, or Flask are used.
4. (Optional) Set up a virtual environment:
	```bash
	python3 -m venv venv
	source venv/bin/activate
	```
5. On macOS, if HTTPS fails, ensure Python certificates are installed or set `verify_tls=False` in config for local testing.


## Usage

You can interact with the system via both the CLI and the built-in Web UI.


### CLI

From the project root (`spiderengine/`):

```bash
python main.py
```

`main.py` adds the project root to `sys.path`, so you normally do **not** need `PYTHONPATH=.`.

### Web UI

To launch the Web UI, ensure the application is running. By default, the Web UI is available at [http://127.0.0.1:8080](http://127.0.0.1:8080).

**Features:**
- Live statistics dashboard (processed, discovered, queue, pending, back-pressure, status)
- Real-time search interface (query indexed pages while crawling continues)
- Modern, responsive design (no external dependencies)

| Command | Description |
|---------|-------------|
| `index <url> <k>` | Start a crawl in the background (max depth `k`). Indexes HTML text into `data/crawler.db` (default path). |
| `search <query>` | Search the index; safe while `index` is running (WAL + read-only connections). |
| `status` | One-line metrics snapshot. |
| `stop` | Cooperative crawl shutdown (no new URLs enqueued). |
| `help` | Short help. |
| `quit` | Exit (stops an active crawl and closes the DB). |


### Example Session

```text
crawler> index http://example.com 1
crawler> search Example
crawler> status
crawler> stop
crawler> quit
```


### Search Result Ranking

Search results are ranked using a custom scoring formula implemented in `crawler/search/relevancy.py`. The score considers:
- **Term frequency** in the document
- **Bonus** if the query appears in the URL
- **Penalty** for greater crawl depth

The Web UI and API now return a `score` field for each result, allowing clients to sort or display result relevance.

While a crawl runs, a background thread prints lines such as:

`[metrics] processed=… discovered=… queued=… pending=… | IDLE` or `THROTTLED (queue_full|rate_limit)`.


## Configuration

Important knobs live in **`crawler/config.py`** (`CrawlConfig`):

- `max_workers`, `max_queue_size`, `fetch_delay_sec`, `fetch_timeout_sec`, `user_agent`, `verify_tls`


Default DB file: **`data/crawler.db`** (`DEFAULT_SQLITE_PATH`). On some macOS Python installs, HTTPS may fail until certificates are installed; you can set `verify_tls=False` in code for **local testing only**.

## Testing

To run tests (if available):

```bash
python -m unittest discover tests
```

Or use your preferred test runner. Ensure the database is in a test-safe state before running tests.

## Contributing

Contributions are welcome! Please open issues or pull requests for bug fixes, improvements, or new features. For major changes, discuss them in an issue first.

## Future Work / Roadmap

- Further enhancements to the Web UI (e.g., crawl control, advanced visualizations)
- Distributed crawling and search
- Advanced relevancy ranking (AI/NLP)
- Integration with external queue/storage systems
- Containerization and cloud deployment

## Project Layout

```
spiderengine/
├── main.py                 # Entry: CLI (adjusts sys.path, then ui.cli)
├── product_prd.md
├── README.md
├── data/                   # SQLite + WAL sidecar files (.gitkeep)
├── ui/
│   ├── cli.py              # Interactive REPL + metrics ticker
│   └── web.py              # Modern Web UI: dashboard, search, metrics
├── crawler/
│   ├── config.py           # CrawlConfig, AppConfig, paths
│   ├── models.py           # CrawledPage, SearchResult, …
│   ├── service.py          # Skeleton (not used by CLI)
│   ├── crawl/              # WebCrawler, fetcher, parser, queue, throttle, visited
│   ├── storage/            # Database (WAL), repositories
│   ├── search/             # Indexer, SearchEngine; relevancy.py stub
│   └── metrics/            # MetricsMonitor, MetricsSnapshot
└── tests/
```


## Architecture

### Strategic Design Choice: CLI (Control Plane) vs Web UI (Data Plane)

This system is architected with a deliberate **Separation of Concerns** between the CLI and the Web UI, prioritizing **System Resilience** over a monolithic "All-in-One" web approach.

- **CLI as Control Plane (Master):**
	- The CLI acts as the authoritative **Master** process, orchestrating all crawling operations, resource allocation, and state transitions.
	- This ensures **crawling stability** and robust **Resource Stewardship**, preventing UI-related bottlenecks or interference with core crawling logic.
	- The CLI is responsible for all control commands, crawl lifecycle management, and direct interaction with the crawler engine.
	- By isolating control logic, the system achieves strong **Fault Isolation**—transient UI or monitoring issues cannot impact crawl progress or data integrity.

- **Web UI as Data Plane (Non-blocking Monitor):**
	- The Web UI is designed as a **Non-blocking Monitor** for real-time metrics and search.
	- It provides a responsive dashboard and search interface, but does not participate in crawl control or critical path operations.
	- The Web UI consumes metrics and search data passively, ensuring that user interactions or UI failures do not affect the stability or throughput of the crawler.

**Why this Architecture?**

- **System Resilience:** By decoupling the Control Plane (CLI) from the Data Plane (Web UI), the system is resilient to UI faults, browser disconnects, or web server restarts.
- **Separation of Concerns:** Each component is focused on its core responsibility, simplifying reasoning, testing, and maintenance.
- **Fault Isolation:** Failures in the Web UI cannot propagate to the crawler or database, ensuring uninterrupted operation.
- **Resource Stewardship:** The CLI can enforce strict resource limits and back-pressure without being affected by UI load or user activity.

This design is a strategic choice to maximize reliability, maintainability, and operational safety, and is preferred over a monolithic web-based architecture where all control and monitoring are coupled.

- **Back-pressure:** capped worker count, **bounded** `queue.Queue` URL queue (blocking `put` when full), and **`RateLimiter`** spacing between fetches. The CLI reads **`MetricsMonitor.snapshot(crawler)`** for queue-full vs rate-limit **THROTTLED** state. (`BackPressureController` in `throttle.py` exists for future UI hooks but is not driving the live dashboard today.)
- **Search during crawl:** WAL + short write transactions on one writer connection under a lock; **each** search opens a separate read connection (`query_only` where supported).
- **Resume:** Before each `run()`, the crawler clears the in-memory visited set, then merges URLs from `crawl_visited ∪ documents`. Each finished worker task records `crawl_visited` so interrupted runs can skip completed URLs.
- **Core I/O:** `urllib.request`, `html.parser`, `sqlite3` — see `.cursorrules`.

## Review Notes & Limitations

These are intentional or acceptable trade-offs for the assignment; worth knowing for demos and grading:

1. **`python main.py` from another directory** — Still run from `spiderengine/` (or ensure the process cwd / path includes the repo). The `sys.path` fix only adds the directory containing `main.py`.
2. **Search ranking** — Results are now ranked by a custom relevancy score (see `crawler/search/relevancy.py`).
3. **HTTPS / TLS** — Default verification may fail on some systems until the Python cert bundle is fixed; see `verify_tls` above.
4. **CLI + metrics** — `[metrics]` lines can appear between prompts; use `status` for a single clean line.
5. **Unused / stub modules** — `crawler/service.py` is a placeholder. The CLI and Web UI wire `Database`, `Indexer`, `WebCrawler`, and `SearchEngine` directly.
6. **Index size** — A B-tree index on `documents(content)` can grow with large crawls; fine for typical course scales.

## Documentation

- **Scope and acceptance criteria:** [`product_prd.md`](product_prd.md)
- **Engineering rules:** [`.cursorrules`](.cursorrules)


## License

Add a license if you publish the repository publicly.
