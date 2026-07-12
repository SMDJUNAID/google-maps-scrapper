#!/usr/bin/env python3
"""CLI for scraping Google Maps business listings by country and industry."""

import argparse
import sys

from scraper.email_finder import enrich_results_with_emails
from scraper.maps_scraper import save_results, scrape_google_maps
from scraper.models import BusinessListing, ScrapeConfig
from scraper.social_finder import enrich_results_with_social


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps listings for importers/businesses by country and industry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --country India --industry "generic medicine importers"
  python main.py --country Germany --industry "pharmaceutical importers" --max-results 50
  python main.py --country USA --industry "generic medicine distributors" --headed
        """,
    )
    parser.add_argument("--country", required=True, help="Target country (e.g. India, Germany, USA)")
    parser.add_argument(
        "--industry",
        default="generic medicine importers",
        help='Industry or business type to search (default: "generic medicine importers")',
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of unique businesses to scrape (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for CSV and JSON output (default: output)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible window) for debugging",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down Playwright actions by N milliseconds",
    )
    parser.add_argument(
        "--extra-query",
        action="append",
        default=[],
        help="Additional search query to run (can be passed multiple times)",
    )
    parser.add_argument(
        "--fetch-emails",
        action="store_true",
        help="After scraping, visit each business website to find email addresses",
    )
    parser.add_argument(
        "--fetch-social",
        action="store_true",
        help="After scraping, visit each business website to find LinkedIn, Instagram, and WhatsApp links",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.max_results < 1:
        print("Error: --max-results must be at least 1", file=sys.stderr)
        return 1

    config = ScrapeConfig(
        country=args.country,
        industry=args.industry,
        max_results=args.max_results,
        headless=not args.headed,
        slow_mo=args.slow_mo,
        output_dir=args.output_dir,
        extra_queries=args.extra_query,
    )

    print(f"Starting scrape for '{config.industry}' in '{config.country}'...")
    print(f"Max results: {config.max_results}")
    print("-" * 50)

    listings = scrape_google_maps(config)

    if not listings:
        print("\nNo listings found. Try --headed to debug, or adjust country/industry terms.")
        return 1

    if args.fetch_emails or args.fetch_social:
        data = [item.to_dict() for item in listings]

    if args.fetch_emails:
        print("-" * 50)
        print("Fetching emails from business websites...")
        data = enrich_results_with_emails(
            data,
            progress_callback=lambda stage, message, current, total: print(f"  [{current}/{total}] {message}"),
        )

    if args.fetch_social:
        print("-" * 50)
        print("Fetching social profiles from business websites...")
        data = enrich_results_with_social(
            data,
            progress_callback=lambda stage, message, current, total: print(f"  [{current}/{total}] {message}"),
        )

    if args.fetch_emails or args.fetch_social:
        listings = [BusinessListing(**row) for row in data]

    paths = save_results(listings, config.output_dir, config.country, config.industry)

    print("-" * 50)
    print(f"Scraped {len(listings)} businesses")
    print(f"JSON: {paths['json']}")
    print(f"CSV:  {paths['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
