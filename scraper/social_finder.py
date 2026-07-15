"""Extract social media profile links from business websites."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from threading import Lock
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse

from scraper.email_finder import CONTACT_PATHS, DEFAULT_MAX_WORKERS, _fetch_page, _normalize_website

LINKEDIN_PROFILE_RE = re.compile(
    r"https?://(?:[a-z]+\.)?linkedin\.com/(?:company|in|showcase)/[a-zA-Z0-9_\-%]+/?",
    re.IGNORECASE,
)
INSTAGRAM_PROFILE_RE = re.compile(
    r"https?://(?:[a-z]+\.)?instagram\.com/(?!p/|reel/|reels/|stories/|explore/|accounts/|direct/|about/|legal/)[a-zA-Z0-9_.]+/?",
    re.IGNORECASE,
)
WHATSAPP_RE = re.compile(
    r"https?://(?:wa\.me/\d+|api\.whatsapp\.com/send[^\s\"'<>]*|chat\.whatsapp\.com/[a-zA-Z0-9]+)",
    re.IGNORECASE,
)

LINKEDIN_SKIP_PARTS = {
    "share",
    "sharing",
    "legal",
    "jobs",
    "learning",
    "feed",
    "pub",
    "uas",
    "help",
    "about",
}

INSTAGRAM_SKIP_NAMES = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "accounts",
    "direct",
    "about",
    "legal",
    "developer",
    "privacy",
}


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value.strip())


def _normalize_url(url: str, base: str = "") -> str:
    url = unquote(url.strip().strip("\"'"))
    if not url or url.startswith(("javascript:", "mailto:", "tel:", "#")):
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    elif base and not url.startswith(("http://", "https://")):
        url = urljoin(base, url)
    return url


def _is_linkedin_profile(url: str) -> bool:
    parsed = urlparse(url.lower())
    if "linkedin.com" not in parsed.netloc:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return False
    if parts[0] not in {"company", "in", "showcase"}:
        return False
    if parts[1] in LINKEDIN_SKIP_PARTS:
        return False
    return True


def _is_instagram_profile(url: str) -> bool:
    parsed = urlparse(url.lower())
    if "instagram.com" not in parsed.netloc:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 1:
        return False
    username = parts[0]
    if username in INSTAGRAM_SKIP_NAMES or len(username) < 2:
        return False
    return True


def _is_whatsapp_link(url: str) -> bool:
    lower = url.lower()
    if "wa.me/" in lower:
        return bool(re.search(r"wa\.me/\d+", lower))
    if "api.whatsapp.com/send" in lower or "web.whatsapp.com/send" in lower:
        return "phone=" in lower
    if "chat.whatsapp.com/" in lower:
        return True
    return False


def _canonical_linkedin(url: str) -> str:
    match = LINKEDIN_PROFILE_RE.search(url)
    return match.group(0).rstrip("/") if match else ""


def _canonical_instagram(url: str) -> str:
    match = INSTAGRAM_PROFILE_RE.search(url)
    if not match:
        return ""
    return match.group(0).rstrip("/")


def _canonical_whatsapp(url: str) -> str:
    match = WHATSAPP_RE.search(url)
    return match.group(0).rstrip("/") if match else ""


def _extract_social_from_html(html: str, page_url: str) -> dict[str, list[str]]:
    linkedin: list[str] = []
    instagram: list[str] = []
    whatsapp: list[str] = []

    parser = _LinkParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    candidates = list(parser.hrefs)
    for pattern in (LINKEDIN_PROFILE_RE, INSTAGRAM_PROFILE_RE, WHATSAPP_RE):
        candidates.extend(pattern.findall(html))

    for raw in candidates:
        url = _normalize_url(raw, page_url)
        if not url:
            continue

        if _is_linkedin_profile(url):
            canonical = _canonical_linkedin(url)
            if canonical:
                linkedin.append(canonical)
        elif _is_instagram_profile(url):
            canonical = _canonical_instagram(url)
            if canonical:
                instagram.append(canonical)
        elif _is_whatsapp_link(url):
            canonical = _canonical_whatsapp(url)
            if canonical:
                whatsapp.append(canonical)

    return {
        "linkedin": _dedupe_preserve_order(linkedin),
        "instagram": _dedupe_preserve_order(instagram),
        "whatsapp": _dedupe_preserve_order(whatsapp),
    }


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower().rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _merge_social(existing: dict[str, list[str]], found: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {key: list(existing.get(key, [])) for key in ("linkedin", "instagram", "whatsapp")}
    for key in merged:
        merged[key].extend(found.get(key, []))
        merged[key] = _dedupe_preserve_order(merged[key])
    return merged


def find_social_for_website(website: str) -> dict[str, list[str]]:
    """Return LinkedIn, Instagram, and WhatsApp links found on a business website."""
    base_url = _normalize_website(website)
    if not base_url:
        return {"linkedin": [], "instagram": [], "whatsapp": []}

    parsed = urlparse(base_url)
    if not parsed.netloc:
        return {"linkedin": [], "instagram": [], "whatsapp": []}

    collected: dict[str, list[str]] = {"linkedin": [], "instagram": [], "whatsapp": []}

    for path in CONTACT_PATHS:
        page_url = urljoin(base_url, path)
        try:
            html = _fetch_page(page_url)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            continue

        if not html:
            continue

        found = _extract_social_from_html(html, page_url)
        collected = _merge_social(collected, found)

        if any(collected.values()):
            break

    return collected


def links_to_string(links: list[str]) -> str:
    return ", ".join(links)


def enrich_results_with_social(
    results: list[dict],
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[dict]:
    """Fetch social profile links for all scraped businesses that have a website.

    Runs concurrently across businesses — see enrich_results_with_emails
    for the rationale; same pattern here.
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
            progress_callback("fetching_social", f"Fetching social profiles: {name}", current, total)

    def _process(index: int) -> None:
        row = output[index]
        name = row.get("name") or "Unknown"
        website = row.get("website") or ""

        if website:
            social = find_social_for_website(website)
            row["linkedin"] = links_to_string(social["linkedin"])
            row["instagram"] = links_to_string(social["instagram"])
            row["whatsapp"] = links_to_string(social["whatsapp"])
        else:
            row["linkedin"] = row.get("linkedin") or ""
            row["instagram"] = row.get("instagram") or ""
            row["whatsapp"] = row.get("whatsapp") or ""

        _report(name)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process, i) for i in range(len(output))]
        for future in as_completed(futures):
            future.result()

    return output