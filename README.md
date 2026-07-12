# Google Maps Importer Scraper

Scrape business listings from Google Maps by **country** and **industry** using Playwright. Built for finding generic medicine importers, but works for any industry search term.

## Features

- Search Google Maps with multiple query variations for better coverage
- Auto-scroll results to load more listings
- Extract business details: name, address, phone, website, rating, category
- Optionally enrich results with **emails**, **LinkedIn**, **Instagram**, and **WhatsApp** links found on each business website
- Export results to **CSV** and **JSON**
- Configurable country, industry, and max results
- REST API, including a synchronous endpoint that returns the full JSON in one call

## Prerequisites

- Python 3.10+
- Chromium (installed via Playwright)

## Setup

```bash
cd google-maps-importer-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Web UI

Start the web interface:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5050](http://localhost:5050) in your browser.

The form lets you set:
- **Country** — target country
- **Max results** — how many unique businesses to scrape
- **Search strings** — multiple industry terms (e.g. Pharmaceutical importers, Medicine wholesalers)

After scraping completes, results appear in a table with download buttons for **JSON** and **Excel**.

## API

The app exposes two ways to run a scrape: an **async, job-based API** (used by the web UI, good for long scrapes with progress polling) and a **synchronous API** (one request in, one JSON response out).

### Synchronous JSON API (recommended for programmatic use)

`POST /api/scrape/json`

Takes the exact same fields as the UI form, and blocks until the scrape (and any requested enrichment) is done, then returns a **status**, a **dynamic summary message** (the same one shown under the results table in the UI, e.g. "5 businesses found · 3 with emails · 1 with social links"), and the **results array** — the same JSON you'd get from clicking "Download JSON" in the UI, including `email`, `linkedin`, `instagram`, and `whatsapp` fields when the corresponding flags are set.

**Request body:**

```json
{
  "country": "India",
  "max_results": 20,
  "search_strings": ["Pharmaceutical importers", "Medicine wholesalers"],
  "auto_fetch_emails": true,
  "auto_fetch_social": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `country` | string | yes | Target country |
| `max_results` | integer ≥ 1 | yes | Max unique businesses to scrape |
| `search_strings` | array of strings | yes (at least 1) | Industry/business search terms |
| `auto_fetch_emails` | boolean | no (default `false`) | Visit each business website to find emails |
| `auto_fetch_social` | boolean | no (default `false`) | Visit each business website to find LinkedIn/Instagram/WhatsApp links |

**Response:** `200 OK` on success:

```json
{
  "status": "success",
  "message": "5 businesses found · 3 with emails · 1 with social links",
  "results": [
    {
      "name": "Acme Pharma Distributors",
      "address": "123 Main St, Mumbai, India",
      "phone": "+91 22 1234 5678",
      "website": "https://acmepharma.example",
      "rating": "4.5",
      "reviews_count": "120",
      "category": "Pharmaceutical distributor",
      "place_url": "https://www.google.com/maps/place/...",
      "search_query": "Pharmaceutical importers in India",
      "country": "India",
      "industry": "Pharmaceutical importers, Medicine wholesalers",
      "email": "info@acmepharma.example",
      "linkedin": "https://linkedin.com/company/acme-pharma",
      "instagram": "",
      "whatsapp": ""
    }
  ]
}
```

The `message` field's counts are computed dynamically from the actual results every time — `"0 businesses found"` if nothing was scraped, `"1 business found"` (singular) for a single result, and the `with emails` / `with social links` clauses only appear (and only count) when `auto_fetch_emails` / `auto_fetch_social` actually found something, exactly like the UI.

**Error responses:** `400` for invalid input, `500` if the scrape itself fails. Both use the same envelope shape:

```json
{ "status": "error", "message": "Country is required." }
```

⚠️ **This call is synchronous and can be slow.** It doesn't return until every listing has been scraped (and, if requested, every website has been checked for emails/social links). For `max_results` beyond ~20–30, or whenever `auto_fetch_emails`/`auto_fetch_social` is enabled, expect this to take anywhere from tens of seconds to several minutes. Set a generous client-side timeout. If you need progress updates instead of a single blocking call, use the async job API below.

### Async job-based API (used by the web UI)

1. `POST /api/scrape` — same request body as above, returns `{"job_id": "..."}` immediately and starts the scrape in the background.
2. `GET /api/jobs/<job_id>` — poll for status/progress; `results` is populated once available.
3. `POST /api/jobs/<job_id>/fetch-emails` — enrich an already-completed job's results with emails.
4. `POST /api/jobs/<job_id>/fetch-social` — enrich an already-completed job's results with social links.
5. `GET /api/jobs/<job_id>/download/json` or `/download/excel` — download the final results as a file.

### Testing the API

With the server running (`python app.py`), try the synchronous endpoint with a small `max_results` first so it returns quickly:

```bash
curl -X POST http://localhost:5050/api/scrape/json \
  -H "Content-Type: application/json" \
  -d '{
        "country": "India",
        "max_results": 5,
        "search_strings": ["Pharmaceutical distributors"],
        "auto_fetch_emails": true,
        "auto_fetch_social": true
      }' \
  -o results.json

cat results.json | python3 -m json.tool | head -50
```

The top of the file will show `status` and `message`, e.g.:

```json
{
  "status": "success",
  "message": "5 businesses found · 3 with emails · 1 with social links",
  "results": [ ... ]
}
```

Or, to check formatting/content directly without saving to a file:

```bash
curl -s -X POST http://localhost:5050/api/scrape/json \
  -H "Content-Type: application/json" \
  -d '{"country": "India", "max_results": 3, "search_strings": ["Medicine wholesalers"]}' \
  | python3 -m json.tool
```

Just eyeball the summary quickly with `jq` (if installed):

```bash
curl -s -X POST http://localhost:5050/api/scrape/json \
  -H "Content-Type: application/json" \
  -d '{"country": "India", "max_results": 3, "search_strings": ["Medicine wholesalers"]}' \
  | jq '{status, message, count: (.results | length)}'
```

Test error handling (missing required field):

```bash
curl -i -X POST http://localhost:5050/api/scrape/json \
  -H "Content-Type: application/json" \
  -d '{"max_results": 5, "search_strings": ["test"]}'
# expect: HTTP/1.1 400 BAD REQUEST, {"status": "error", "message": "Country is required."}
```

You can also test it against a Python client:

```python
import requests

response = requests.post(
    "http://localhost:5050/api/scrape/json",
    json={
        "country": "Germany",
        "max_results": 10,
        "search_strings": ["Pharmaceutical importers"],
        "auto_fetch_emails": True,
        "auto_fetch_social": True,
    },
    timeout=600,  # generous timeout — this call blocks until the scrape finishes
)
response.raise_for_status()
payload = response.json()
print(payload["status"])   # "success"
print(payload["message"])  # e.g. "10 businesses found · 6 with emails · 2 with social links"
print(f"Got {len(payload['results'])} businesses")
print(payload["results"][0])
```

## Running in VS Code

The UI and the API are the **same Flask app** — `/` serves the UI and `/api/...` serves the API, both on one process/port. You only need to run `app.py` once; there's nothing separate to start for "the API" vs "the UI".

**Option 1 — Integrated terminal (simplest):**
1. Open the project folder in VS Code.
2. Open a terminal (`` Ctrl+` ``), activate the venv, and run:
   ```bash
   source .venv/bin/activate   # .venv\Scripts\activate on Windows
   python app.py
   ```
3. Now both are live at `http://localhost:5050`:
   - UI: open `http://localhost:5050/` in a browser tab.
   - API: hit `http://localhost:5050/api/scrape/json` with `curl`/Postman/`requests` from another terminal or tool — at the same time, if you like.

**Option 2 — VS Code's Run/Debug (F5):**
Add a `.vscode/launch.json` so you can start it with breakpoints:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Flask app",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/app.py",
      "console": "integratedTerminal",
      "justMyCode": true
    }
  ]
}
```
Press `F5` (make sure the venv is selected as the interpreter, bottom-right of VS Code), and it runs the same single server — again, UI and API both available immediately.

**Concurrency note:** `/api/scrape/json` blocks for the duration of a scrape, so `app.run(..., threaded=True)` is set in `app.py` — this lets the dev server handle the UI and an in-flight API call (or multiple API calls) at the same time instead of queuing them one after another. If you ever swap the dev server for something like `gunicorn`/`waitress` in production, use multiple workers/threads there too for the same reason.



### Basic — generic medicine importers in a country

```bash
python main.py --country India --industry "generic medicine importers"
```

### Custom industry and limit

```bash
python main.py --country Germany --industry "pharmaceutical importers" --max-results 50
```

### Debug with visible browser

```bash
python main.py --country USA --industry "generic medicine distributors" --headed
```

### Add extra search queries

```bash
python main.py --country Brazil --industry "generic medicine importers" \
  --extra-query "API importer pharmaceuticals Brazil" \
  --extra-query "bulk medicine supplier Brazil"
```

## Output

Results are saved to the `output/` folder:

| Field | Description |
|-------|-------------|
| `name` | Business name |
| `address` | Full address |
| `phone` | Phone number |
| `website` | Website URL |
| `rating` | Star rating |
| `reviews_count` | Number of reviews |
| `category` | Business category |
| `place_url` | Google Maps place URL |
| `search_query` | Query that found this listing |
| `country` | Target country |
| `industry` | Target industry |
| `email` | Email found on website (if enrichment enabled) |
| `linkedin` | LinkedIn profile URL(s) found on website |
| `instagram` | Instagram profile URL(s) found on website |
| `whatsapp` | WhatsApp link(s) found on website |

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--country` | *(required)* | Target country |
| `--industry` | `generic medicine importers` | Business type to search |
| `--max-results` | `100` | Max unique businesses |
| `--output-dir` | `output` | Output directory |
| `--headed` | off | Show browser window |
| `--slow-mo` | `0` | Slow actions (ms) |
| `--extra-query` | — | Additional search query (repeatable) |
| `--fetch-emails` | off | Fetch emails from business websites after scraping |
| `--fetch-social` | off | Fetch LinkedIn/Instagram/WhatsApp links from business websites after scraping |

## Important Notes

1. **Google Terms of Service**: Automated scraping of Google Maps may violate Google's Terms of Service. Use this tool responsibly, for personal/research purposes, and respect rate limits.
2. **Results vary**: Google Maps does not have a dedicated "importers" category. Results depend on how businesses list themselves (pharmacy, distributor, wholesaler, etc.).
3. **CAPTCHAs / blocking**: Google may show consent dialogs or block automated access. Use `--headed` to complete CAPTCHAs manually if needed.
4. **Not exhaustive**: Google Maps returns a limited set per search. Use `--extra-query` and different industry terms to broaden coverage.
5. **Synchronous API and timeouts**: `/api/scrape/json` blocks for the full duration of the scrape. If you're calling it from a reverse proxy, load balancer, or serverless function, make sure request timeouts are set generously (several minutes) or use the async job API instead.

## Troubleshooting

- **No results**: Try broader terms like `"pharmaceutical distributor"` or `"medicine wholesaler"`.
- **Browser issues**: Re-run `playwright install chromium`.
- **Blocked by Google**: Add delays with `--slow-mo 200`, use `--headed`, or try again later.
- **`/api/scrape/json` times out on the client side**: Increase your HTTP client's timeout, reduce `max_results`, or switch to the async `/api/scrape` + `/api/jobs/<id>` polling flow for large scrapes.
- **`auto_fetch_emails`/`auto_fetch_social` makes the request take a long time with no response yet (e.g. in Postman)**: This is expected, not a bug. For each business, the scraper checks up to 7 possible pages on its website (home, `/contact`, `/about`, etc.), each with a 12-second timeout, until one responds — so a handful of slow or unreachable websites can add minutes to the total. Watch your terminal for `[fetching_emails] N/total ...` / `[fetching_social] N/total ...` lines to confirm it's still working rather than hung. If you want live progress instead of one long blocking Postman request, use the async flow: `POST /api/scrape` (with the same body) to get a `job_id`, then poll `GET /api/jobs/<job_id>` every couple seconds to watch `stage`/`current`/`total`/`message` update in real time.