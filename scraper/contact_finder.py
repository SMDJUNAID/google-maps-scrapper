"""Combined email + social profile extraction in a single website crawl.

When both auto_fetch_emails and auto_fetch_social are requested,
enrich_results_with_emails() and enrich_results_with_social() used to each
independently crawl the same set of pages on a business's website — once
to look for emails, once to look for social links — doubling the HTTP
requests for no reason. This module fetches each page once and extracts
both from the same HTML, and runs across businesses concurrently.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse

from scraper.email_finder import (
    CONTACT_PATHS,
    DEFAULT_MAX_WORKERS,
    _extract_emails_from_html,
    _fetch_page,
    _normalize_website,
    emails_to_string,
)
from scraper.social_finder import _extract_social_from_html, _merge_social, links_to_string

_EMPTY_SOCIAL = {"linkedin": [], "instagram": [], "whatsapp": []}


def _find_contact_data_for_website(website: str) -> dict:
    """Crawl a website's likely contact pages once, extracting both emails
    and social links from each page fetched, stopping as soon as both have
    at least one hit (or the paths run out).
    """
    base_url = _normalize_website(website)
    if not base_url:
        return {"emails": [], "social": dict(_EMPTY_SOCIAL)}

    parsed = urlparse(base_url)
    if not parsed.netloc:
        return {"emails": [], "social": dict(_EMPTY_SOCIAL)}

    seen_emails: set[str] = set()
    emails: list[str] = []
    social: dict[str, list[str]] = dict(_EMPTY_SOCIAL)

    for path in CONTACT_PATHS:
        page_url = urljoin(base_url, path)
        try:
            html = _fetch_page(page_url)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            continue
        if not html:
            continue

        for email in _extract_emails_from_html(html):
            key = email.lower()
            if key not in seen_emails:
                seen_emails.add(key)
                emails.append(email)

        found_social = _extract_social_from_html(html, page_url)
        social = _merge_social(social, found_social)

        if emails and any(social.values()):
            break

    return {"emails": emails, "social": social}


def enrich_results_combined(
    results: list[dict],
    fetch_emails: bool = True,
    fetch_social: bool = True,
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[dict]:
    """Fetch emails and/or social links for all rows with a website in one
    crawl per business, running concurrently across businesses.

    Use this instead of calling enrich_results_with_emails() followed by
    enrich_results_with_social() whenever both are needed — it does the
    same job with roughly half the HTTP requests plus concurrency.
    """
    total = len(results)
    output = [dict(row) for row in results]

    if not output:
        return output

    completed = 0
    lock = Lock()

    def _report(name: str) -> None:
        nonlocal completed
        with lock:
            completed += 1
            current = completed
        if progress_callback:
            progress_callback("fetching_contact_info", f"Fetching contact info: {name}", current, total)

    def _process(index: int) -> None:
        row = output[index]
        name = row.get("name") or "Unknown"
        website = row.get("website") or ""

        if website:
            data = _find_contact_data_for_website(website)
            if fetch_emails:
                row["email"] = emails_to_string(data["emails"])
            if fetch_social:
                row["linkedin"] = links_to_string(data["social"]["linkedin"])
                row["instagram"] = links_to_string(data["social"]["instagram"])
                row["whatsapp"] = links_to_string(data["social"]["whatsapp"])
        else:
            if fetch_emails:
                row["email"] = row.get("email") or ""
            if fetch_social:
                row["linkedin"] = row.get("linkedin") or ""
                row["instagram"] = row.get("instagram") or ""
                row["whatsapp"] = row.get("whatsapp") or ""

        _report(name)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process, i) for i in range(len(output))]
        for future in as_completed(futures):
            future.result()

    return output