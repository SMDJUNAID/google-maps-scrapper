"""Extract business emails from company websites."""

from __future__ import annotations

import re
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from threading import Lock
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

BLOCKED_EMAIL_DOMAINS = {
    "example.com",
    "domain.com",
    "email.com",
    "sentry.io",
    "wixpress.com",
    "schema.org",
    "w3.org",
    "googleusercontent.com",
    "gstatic.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "youtube.com",
    "linkedin.com",
    "cloudflare.com",
    "wordpress.com",
    "squarespace.com",
}

BLOCKED_LOCAL_PARTS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
    "webmaster",
    "admin",
    "support",
    "sentry",
}

CONTACT_PATHS = ("", "/contact", "/contact-us", "/about", "/about-us", "/en/contact", "/en/about")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 8  # was 12s — trimmed since most sites respond well under this;
                      # slow/unreachable sites now waste less time per path.

DEFAULT_MAX_WORKERS = 8  # how many businesses to enrich concurrently


class _MailtoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.mailtos: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value and value.lower().startswith("mailto:"):
                email = value[7:].split("?")[0].strip()
                if email:
                    self.mailtos.append(email)


def _normalize_website(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _is_valid_email(email: str) -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False

    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False

    if domain in BLOCKED_EMAIL_DOMAINS:
        return False

    if any(domain.endswith(f".{blocked}") for blocked in BLOCKED_EMAIL_DOMAINS):
        return False

    if local in BLOCKED_LOCAL_PARTS:
        return False

    if re.search(r"\.(png|jpg|jpeg|gif|svg|webp|css|js)$", email):
        return False

    return True


def _extract_emails_from_html(html: str) -> list[str]:
    found: list[str] = []

    parser = _MailtoParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    found.extend(parser.mailtos)

    for match in EMAIL_PATTERN.findall(html):
        found.append(match)

    unique: list[str] = []
    seen: set[str] = set()
    for email in found:
        cleaned = email.strip().rstrip(".,;)")
        if not _is_valid_email(cleaned):
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cleaned)

    return unique


def _fetch_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urlopen(request, timeout=REQUEST_TIMEOUT, context=context) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text" not in content_type and "html" not in content_type:
            return ""
        raw = response.read(500_000)
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return raw.decode("latin-1", errors="ignore")


def find_emails_for_website(website: str) -> list[str]:
    """Return unique emails found on a business website."""
    base_url = _normalize_website(website)
    if not base_url:
        return []

    parsed = urlparse(base_url)
    if not parsed.netloc:
        return []

    all_emails: list[str] = []
    seen: set[str] = set()

    for path in CONTACT_PATHS:
        page_url = urljoin(base_url, path)
        try:
            html = _fetch_page(page_url)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            continue

        for email in _extract_emails_from_html(html):
            key = email.lower()
            if key not in seen:
                seen.add(key)
                all_emails.append(email)

        if all_emails:
            break

    return all_emails


def emails_to_string(emails: list[str]) -> str:
    return ", ".join(emails)


def enrich_results_with_emails(
    results: list[dict],
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[dict]:
    """Fetch emails for all scraped businesses that have a website.

    Runs concurrently across businesses (each website fetch is independent
    I/O-bound work), which is the main lever for speeding this up — it's
    the same total network work, just not serialized one business at a
    time. Progress is still reported as each business finishes, though the
    completion order may differ from the input order since they run in
    parallel.
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
            progress_callback("fetching_emails", f"Fetching emails: {name}", current, total)

    def _process(index: int) -> None:
        row = output[index]
        name = row.get("name") or "Unknown"
        website = row.get("website") or ""

        if website:
            emails = find_emails_for_website(website)
            row["email"] = emails_to_string(emails)
        else:
            row["email"] = row.get("email") or ""

        _report(name)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process, i) for i in range(len(output))]
        for future in as_completed(futures):
            future.result()  # re-raise any exception from a worker

    return output