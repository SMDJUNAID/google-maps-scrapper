# Google Maps Importer Scraper

Scrape business listings from Google Maps by **country** and **industry** using Playwright. Built for finding generic medicine importers, but works for any industry search term.

## Features

- Search Google Maps with multiple query variations for better coverage
- Auto-scroll results to load more listings
- Extract business details: name, address, phone, website, rating, category
- Export results to **CSV** and **JSON**
- Configurable country, industry, and max results

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

## Usage (CLI)

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

## Important Notes

1. **Google Terms of Service**: Automated scraping of Google Maps may violate Google's Terms of Service. Use this tool responsibly, for personal/research purposes, and respect rate limits.
2. **Results vary**: Google Maps does not have a dedicated "importers" category. Results depend on how businesses list themselves (pharmacy, distributor, wholesaler, etc.).
3. **CAPTCHAs / blocking**: Google may show consent dialogs or block automated access. Use `--headed` to complete CAPTCHAs manually if needed.
4. **Not exhaustive**: Google Maps returns a limited set per search. Use `--extra-query` and different industry terms to broaden coverage.

## Troubleshooting

- **No results**: Try broader terms like `"pharmaceutical distributor"` or `"medicine wholesaler"`.
- **Browser issues**: Re-run `playwright install chromium`.
- **Blocked by Google**: Add delays with `--slow-mo 200`, use `--headed`, or try again later.
