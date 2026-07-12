"""Google Maps business listing scraper using Playwright."""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from scraper.models import BusinessListing, ScrapeConfig

FEED_SELECTOR = 'div[role="feed"]'
PLACE_LINK_SELECTOR = 'a[href*="/maps/place/"]'
END_OF_LIST_TEXT = "You've reached the end of the list"


def build_search_queries(
    country: str,
    industry: str,
    extra: list[str] | None = None,
    search_strings: list[str] | None = None,
) -> list[str]:
    """Build search queries from custom search strings or default importer variations."""
    country = country.strip()
    queries: list[str] = []

    if search_strings:
        for term in search_strings:
            term = term.strip()
            if not term:
                continue
            if country.lower() in term.lower():
                queries.append(term)
            else:
                queries.append(f"{term} in {country}")
    else:
        base = industry.strip()
        queries = [
            f"{base} in {country}",
            f"{base} {country}",
            f"pharmaceutical importers in {country}",
            f"generic medicine distributors in {country}",
            f"medicine import company in {country}",
        ]

    if extra:
        queries.extend(extra)

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        normalized = query.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(query)
    return unique


def _dismiss_consent_if_present(page: Page) -> None:
    for selector in (
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
        'button:has-text("I agree")',
        '[aria-label="Accept all"]',
    ):
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=2000):
                button.click()
                page.wait_for_timeout(1000)
                return
        except PlaywrightTimeout:
            continue


def _scroll_results_feed(page: Page, max_scrolls: int = 50) -> int:
    feed = page.locator(FEED_SELECTOR)
    try:
        feed.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        return 0

    previous_count = 0
    stable_rounds = 0

    for _ in range(max_scrolls):
        if page.locator(f"text={END_OF_LIST_TEXT}").count() > 0:
            break

        feed.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(1500)

        current_count = page.locator(f"{FEED_SELECTOR} {PLACE_LINK_SELECTOR}").count()
        if current_count == previous_count:
            stable_rounds += 1
            if stable_rounds >= 3:
                break
        else:
            stable_rounds = 0
            previous_count = current_count

    return page.locator(f"{FEED_SELECTOR} {PLACE_LINK_SELECTOR}").count()


def _collect_place_links(page: Page, limit: int) -> list[dict[str, str]]:
    links = page.locator(f"{FEED_SELECTOR} {PLACE_LINK_SELECTOR}")
    count = min(links.count(), limit)
    places: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for index in range(count):
        link = links.nth(index)
        href = link.get_attribute("href") or ""
        if not href or href in seen_urls:
            continue

        aria = link.get_attribute("aria-label") or ""
        name = aria.split("·")[0].strip() if aria else ""
        if not name:
            name = link.inner_text().strip().split("\n")[0]

        seen_urls.add(href)
        places.append({"name": name, "url": href, "aria_label": aria})

    return places


def _clean_text(text: str) -> str:
    """Remove Google Maps icon glyphs and normalize whitespace."""
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_text(locator) -> str:
    try:
        if locator.count() == 0:
            return ""
        return _clean_text(locator.first.inner_text())
    except Exception:
        return ""


def _extract_place_details(page: Page, place: dict[str, str], config: ScrapeConfig) -> BusinessListing:
    listing = BusinessListing(
        name=place.get("name", ""),
        place_url=place.get("url", ""),
        search_query=place.get("search_query", ""),
        country=config.country,
        industry=config.industry,
    )

    try:
        page.goto(place["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        _dismiss_consent_if_present(page)
    except PlaywrightTimeout:
        return listing

    name = _extract_text(page.locator("h1"))
    if name:
        listing.name = name

    address = _extract_text(page.locator('button[data-item-id="address"]'))
    if not address:
        address = _extract_text(page.locator('[data-item-id="address"]'))
    listing.address = address

    phone = _extract_text(page.locator('button[data-item-id^="phone"]'))
    if not phone:
        phone = _extract_text(page.locator('[data-tooltip="Copy phone number"]'))
    listing.phone = phone

    website_locator = page.locator('a[data-item-id="authority"]')
    if website_locator.count() > 0:
        listing.website = website_locator.first.get_attribute("href") or ""
    else:
        listing.website = _extract_text(page.locator('a[aria-label*="Website"]'))

    rating_block = page.locator('div[role="img"][aria-label*="stars"]')
    if rating_block.count() > 0:
        aria = rating_block.first.get_attribute("aria-label") or ""
        rating_match = re.search(r"([\d.]+)\s*stars?", aria, re.I)
        reviews_match = re.search(r"([\d,]+)\s*reviews?", aria, re.I)
        if rating_match:
            listing.rating = rating_match.group(1)
        if reviews_match:
            listing.reviews_count = reviews_match.group(1).replace(",", "")

    category = _extract_text(page.locator("button[jsaction*='category']"))
    if not category:
        category = _extract_text(page.locator('button[aria-label*="Category"]'))
    listing.category = category

    return listing


def _search_and_collect(
    page: Page,
    query: str,
    config: ScrapeConfig,
    remaining: int,
) -> list[dict[str, str]]:
    if remaining <= 0:
        return []

    search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)
    _dismiss_consent_if_present(page)

    _scroll_results_feed(page)
    places = _collect_place_links(page, remaining)
    for place in places:
        place["search_query"] = query
    return places


def scrape_google_maps(
    config: ScrapeConfig,
    progress_callback: Callable[[str, str, int, int], None] | None = None,
) -> list[BusinessListing]:
    def _report(stage: str, message: str, current: int = 0, total: int = 0) -> None:
        if progress_callback:
            progress_callback(stage, message, current, total)

    queries = build_search_queries(
        config.country,
        config.industry,
        config.extra_queries,
        config.search_strings,
    )
    all_places: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless, slow_mo=config.slow_mo)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for query in queries:
            remaining = config.max_results - len(all_places)
            if remaining <= 0:
                break

            print(f"Searching: {query}")
            _report("searching", f"Searching: {query}", len(all_places), config.max_results)
            places = _search_and_collect(page, query, config, remaining)
            for place in places:
                url = place["url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_places.append(place)

            print(f"  Found {len(places)} listings ({len(all_places)} total unique)")
            _report("searching", f"Found {len(all_places)} unique listings so far", len(all_places), config.max_results)

        listings: list[BusinessListing] = []
        total = len(all_places)

        for index, place in enumerate(all_places, start=1):
            name = place.get("name", "Unknown")
            print(f"Extracting details {index}/{total}: {name}")
            _report("extracting", f"Extracting details: {name}", index, total)
            listing = _extract_place_details(page, place, config)
            listings.append(listing)
            page.wait_for_timeout(800)

        context.close()
        browser.close()

    return listings


def save_results(listings: list[BusinessListing], output_dir: str, country: str, industry: str) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]+", "_", f"{country}_{industry}".lower()).strip("_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = f"{slug}_{timestamp}"

    json_path = out / f"{base_name}.json"
    csv_path = out / f"{base_name}.csv"

    data = [item.to_dict() for item in listings]
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = list(BusinessListing.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    return {"json": str(json_path), "csv": str(csv_path)}
