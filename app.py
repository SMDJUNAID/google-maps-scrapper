#!/usr/bin/env python3
"""Web UI for Google Maps business listing scraper."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from flask_migrate import Migrate

from config import get_config
from extensions import db
from models import Company, Contact, SearchJob, SearchResult
from search_history import _record_activity, process_due_email_work, search_history_bp
from scraper.contact_finder import enrich_results_combined
from scraper.email_finder import enrich_results_with_emails
from scraper.export import to_excel_bytes_from_dicts, to_json_bytes_from_dicts
from scraper.maps_scraper import scrape_google_maps
from scraper.models import ScrapeConfig
from scraper.social_finder import enrich_results_with_social

app = Flask(__name__)
app.config.from_object(get_config())

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# Register blueprints
app.register_blueprint(search_history_bp)


@app.before_request
def ensure_email_scheduler_running():
    _start_email_scheduler()

DEFAULT_SEARCH_STRINGS = [
    "Pharmaceutical importers",
    "Pharmaceutical distributors",
    "Medicine wholesalers",
    "Drug distributors",
    "Medical supply companies",
    "Pharmaceutical suppliers",
]


@dataclass
class ScrapeJob:
    id: str
    status: str = "pending"
    message: str = "Starting scrape..."
    stage: str = "pending"
    current: int = 0
    total: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    country: str = ""
    max_results: int = 0
    search_strings: list[str] = field(default_factory=list)


jobs: dict[str, ScrapeJob] = {}
jobs_lock = threading.Lock()
email_scheduler_started = False
email_scheduler_lock = threading.Lock()

SEARCH_JOB_UPDATE_COLUMNS = {
    "status",
    "message",
    "stage",
    "current",
    "total",
    "error",
    "country",
    "state",
    "city",
    "industry",
    "max_results",
    "search_strings",
    "auto_fetch_emails",
    "auto_fetch_social",
    "completed_at",
}


def _email_scheduler_loop() -> None:
    interval = max(15, int(app.config.get("EMAIL_SCHEDULER_INTERVAL_SECONDS", 60)))
    while True:
        time.sleep(interval)
        with app.app_context():
            try:
                process_due_email_work()
            except Exception as exc:
                app.logger.error("Email scheduler failed: %s", exc)


def _start_email_scheduler() -> None:
    global email_scheduler_started
    if not app.config.get("EMAIL_SCHEDULER_ENABLED", True):
        return
    with email_scheduler_lock:
        if email_scheduler_started:
            return
        email_scheduler_started = True
        thread = threading.Thread(target=_email_scheduler_loop, daemon=True)
        thread.start()


def _validate_scrape_payload(payload: dict[str, Any]) -> tuple[Any, int] | None:
    """Return a Flask error response (json, status) if the payload is invalid, else None."""
    country = (payload.get("country") or "").strip()
    max_results = payload.get("max_results", 100)
    search_strings = payload.get("search_strings") or []

    if not country:
        return jsonify({"error": "Country is required."}), 400

    if not isinstance(max_results, int) or max_results < 1:
        return jsonify({"error": "Max results must be a positive integer."}), 400

    cleaned_strings = [s.strip() for s in search_strings if isinstance(s, str) and s.strip()]
    if not cleaned_strings:
        return jsonify({"error": "At least one search string is required."}), 400

    return None


def _config_from_payload(payload: dict[str, Any]) -> ScrapeConfig:
    """Build a ScrapeConfig from an already-validated request payload."""
    country = (payload.get("country") or "").strip()
    max_results = payload.get("max_results", 100)
    search_strings = payload.get("search_strings") or []

    cleaned_strings = [s.strip() for s in search_strings if isinstance(s, str) and s.strip()]
    industry_label = ", ".join(cleaned_strings[:3])
    if len(cleaned_strings) > 3:
        industry_label += f" (+{len(cleaned_strings) - 3} more)"

    return ScrapeConfig(
        country=country,
        industry=industry_label,
        max_results=max_results,
        search_strings=cleaned_strings,
        headless=True,
    )


def _execute_scrape_sync(
    config: ScrapeConfig,
    auto_fetch_emails: bool = False,
    auto_fetch_social: bool = False,
) -> list[dict[str, Any]]:
    """Run a scrape (and optional enrichment) synchronously, returning the result rows.

    This is the same pipeline the background job uses, but it blocks and
    hands back the final data directly instead of writing progress to a
    ScrapeJob. Used by the synchronous JSON API endpoint.

    A console progress callback is wired up for every stage (scraping,
    email enrichment, social enrichment) so long-running requests print
    visible progress in the terminal instead of appearing to hang —
    email/social enrichment in particular can take a while per business
    since each website is checked over several possible contact pages.

    When both auto_fetch_emails and auto_fetch_social are requested, this
    uses enrich_results_combined() to crawl each website once for both
    instead of twice, and every enrichment path runs businesses
    concurrently — see scraper/contact_finder.py, scraper/email_finder.py,
    and scraper/social_finder.py.
    """

    def _log_progress(stage: str, message: str, current: int, total: int) -> None:
        print(f"[{stage}] {current}/{total} {message}")

    listings = scrape_google_maps(config, progress_callback=_log_progress)
    data = [item.to_dict() for item in listings]

    if not data:
        return data

    if auto_fetch_emails and auto_fetch_social:
        print(f"Fetching emails + social profiles for {len(data)} businesses (combined, concurrent)...")
        data = enrich_results_combined(
            data, fetch_emails=True, fetch_social=True, progress_callback=_log_progress
        )
    elif auto_fetch_emails:
        print(f"Fetching emails for {len(data)} businesses...")
        data = enrich_results_with_emails(data, progress_callback=_log_progress)
    elif auto_fetch_social:
        print(f"Fetching social profiles for {len(data)} businesses...")
        data = enrich_results_with_social(data, progress_callback=_log_progress)

    return data


def _build_summary_message(results: list[dict[str, Any]]) -> str:
    """Build the same high-level summary the UI shows under the results table,
    e.g. "5 businesses found · 3 with emails · 1 with social links".
    """
    count = len(results)
    with_emails = sum(1 for row in results if row.get("email"))
    with_social = sum(
        1 for row in results if row.get("linkedin") or row.get("instagram") or row.get("whatsapp")
    )

    extras = []
    if with_emails:
        extras.append(f"{with_emails} with emails")
    if with_social:
        extras.append(f"{with_social} with social links")

    noun = "business" if count == 1 else "businesses"
    message = f"{count} {noun} found"
    if extras:
        message += " · " + " · ".join(extras)
    return message


def _update_job(job_id: str, **kwargs: Any) -> None:
    if kwargs.get("status") in {"completed", "failed"} and not kwargs.get("completed_at"):
        kwargs["completed_at"] = datetime.now(timezone.utc)

    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)

    # Also update scalar database columns. Relationship fields such as
    # SearchJob.results must be written via _save_results_to_database().
    with app.app_context():
        db_job = db.session.get(SearchJob, job_id)
        if db_job:
            for key, value in kwargs.items():
                if key in SEARCH_JOB_UPDATE_COLUMNS:
                    setattr(db_job, key, value)
            db.session.commit()


def _run_social_enrichment(job_id: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def on_progress(stage: str, message: str, current: int, total: int) -> None:
        _update_job(
            job_id,
            status="running",
            stage=stage,
            message=message,
            current=current,
            total=total,
        )

    _update_job(
        job_id,
        status="running",
        stage="fetching_social",
        message="Starting social profile enrichment...",
        current=0,
        total=len(results),
    )
    enriched = enrich_results_with_social(results, progress_callback=on_progress)
    with_social = sum(
        1 for row in enriched if row.get("linkedin") or row.get("instagram") or row.get("whatsapp")
    )
    _update_job(
        job_id,
        status="completed",
        stage="done",
        message=f"Social fetch complete — {with_social} of {len(enriched)} businesses have social links.",
        results=enriched,
        current=len(enriched),
        total=len(enriched),
        error=None,
    )
    # Save enriched results to database
    _save_results_to_database(job_id, enriched)
    return enriched


def _run_combined_enrichment(job_id: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def on_progress(stage: str, message: str, current: int, total: int) -> None:
        _update_job(
            job_id,
            status="running",
            stage=stage,
            message=message,
            current=current,
            total=total,
        )

    _update_job(
        job_id,
        status="running",
        stage="fetching_contact_info",
        message="Starting email + social profile enrichment...",
        current=0,
        total=len(results),
    )
    enriched = enrich_results_combined(
        results, fetch_emails=True, fetch_social=True, progress_callback=on_progress
    )
    with_emails = sum(1 for row in enriched if row.get("email"))
    with_social = sum(
        1 for row in enriched if row.get("linkedin") or row.get("instagram") or row.get("whatsapp")
    )
    _update_job(
        job_id,
        status="completed",
        stage="done",
        message=(
            f"Enrichment complete — {with_emails} of {len(enriched)} businesses have emails, "
            f"{with_social} have social links."
        ),
        results=enriched,
        current=len(enriched),
        total=len(enriched),
        error=None,
    )
    # Save enriched results to database
    _save_results_to_database(job_id, enriched)
    return enriched


def _run_email_enrichment(job_id: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def on_progress(stage: str, message: str, current: int, total: int) -> None:
        _update_job(
            job_id,
            status="running",
            stage=stage,
            message=message,
            current=current,
            total=total,
        )

    try:
        _update_job(
            job_id,
            status="running",
            stage="fetching_emails",
            message="Starting email enrichment...",
            current=0,
            total=len(results),
        )
        enriched = enrich_results_with_emails(results, progress_callback=on_progress)
        with_emails = sum(1 for row in enriched if row.get("email"))
        _update_job(
            job_id,
            results=enriched,
            current=len(enriched),
            total=len(enriched),
            message=f"Email fetch complete — {with_emails} of {len(enriched)} businesses have emails.",
            error=None,
        )
        # Save enriched results to database
        _save_results_to_database(job_id, enriched)
        return enriched
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="error",
            message="Email fetch failed.",
            error=str(exc),
        )
        raise


def _run_email_enrichment_task(job_id: str, results: list[dict[str, Any]]) -> None:
    try:
        _run_email_enrichment(job_id, results)
        _update_job(job_id, status="completed", stage="done")
    except Exception:
        pass


def _run_social_enrichment_task(job_id: str, results: list[dict[str, Any]]) -> None:
    try:
        _run_social_enrichment(job_id, results)
    except Exception:
        _update_job(
            job_id,
            status="failed",
            stage="error",
            message="Social fetch failed.",
            error="Social enrichment failed.",
        )


def _run_post_scrape_enrichment(
    job_id: str,
    results: list[dict[str, Any]],
    auto_fetch_emails: bool,
    auto_fetch_social: bool,
) -> None:
    try:
        if auto_fetch_emails and auto_fetch_social:
            _run_combined_enrichment(job_id, results)
            return
        if auto_fetch_emails:
            _run_email_enrichment(job_id, results)
            _update_job(job_id, status="completed", stage="done")
            return
        if auto_fetch_social:
            _run_social_enrichment(job_id, results)
            return
    except Exception:
        return


def _clean_optional_text(value: Any) -> str | None:
    """Store missing optional unique fields as NULL, not empty strings."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _save_results_to_database(job_id: str, results: list[dict[str, Any]]) -> None:
    """Save scrape results to database using new models with duplicate detection."""
    with app.app_context():
        db_job = db.session.get(SearchJob, job_id)
        # Clear existing results for this job
        SearchResult.query.filter_by(search_job_id=job_id).delete()
        
        # Add new results
        for result in results:
            # Find or create company using place_url and website for duplicate detection
            place_url = _clean_optional_text(result.get("place_url"))
            website = _clean_optional_text(result.get("website"))
            state = _clean_optional_text(result.get("state") or (db_job.state if db_job else None))
            city = _clean_optional_text(result.get("city") or (db_job.city if db_job else None))
            
            company = None
            if place_url:
                company = Company.query.filter_by(place_url=place_url).first()
            elif website:
                company = Company.query.filter_by(website=website).first()
            
            if not company:
                company = Company(
                    name=result.get("name", ""),
                    address=result.get("address", ""),
                    website=website,
                    category=result.get("category", ""),
                    rating=result.get("rating", ""),
                    reviews_count=result.get("reviews_count", ""),
                    place_url=place_url,
                    country=result.get("country", ""),
                    industry=result.get("industry", ""),
                )
                db.session.add(company)
                db.session.flush()  # Get the company ID
                company.state = state
                company.city = city
                _record_activity(
                    company.id,
                    "company_created",
                    f"Company created from search job {job_id}.",
                    user="System",
                    metadata={"search_job_id": job_id},
                )
            else:
                # Update existing company with fresh data
                before = {
                    "name": company.name,
                    "address": company.address,
                    "category": company.category,
                    "rating": company.rating,
                    "reviews_count": company.reviews_count,
                    "country": company.country,
                    "state": company.state,
                    "city": company.city,
                    "industry": company.industry,
                    "website": company.website,
                    "place_url": company.place_url,
                }
                company.name = result.get("name", company.name)
                company.address = result.get("address", company.address)
                company.category = result.get("category", company.category)
                company.rating = result.get("rating", company.rating)
                company.reviews_count = result.get("reviews_count", company.reviews_count)
                company.country = result.get("country", company.country)
                company.state = state or company.state
                company.city = city or company.city
                company.industry = result.get("industry", company.industry)
                if website and not company.website:
                    company.website = website
                if place_url and not company.place_url:
                    company.place_url = place_url
                changed_fields = [
                    field for field, old_value in before.items()
                    if getattr(company, field) != old_value
                ]
                if changed_fields:
                    _record_activity(
                        company.id,
                        "company_updated",
                        f"Company updated from search job {job_id}.",
                        user="System",
                        metadata={"search_job_id": job_id, "fields": changed_fields},
                    )
            
            # Keep one current general contact per company. Re-scrapes update
            # the latest contact row instead of adding another card every time.
            if result.get("phone") or result.get("email") or result.get("linkedin") or result.get("instagram") or result.get("whatsapp"):
                contact = (
                    Contact.query.filter_by(company_id=company.id, contact_type="general")
                    .order_by(Contact.updated_at.desc(), Contact.created_at.desc(), Contact.id.desc())
                    .first()
                )
                if not contact:
                    contact = Contact(company_id=company.id, contact_type="general")
                    db.session.add(contact)

                contact.phone = result.get("phone", "") or contact.phone
                contact.email = result.get("email", "") or contact.email
                contact.linkedin = result.get("linkedin", "") or contact.linkedin
                contact.instagram = result.get("instagram", "") or contact.instagram
                contact.whatsapp = result.get("whatsapp", "") or contact.whatsapp
            
            # Create search result
            search_result = SearchResult(
                search_job_id=job_id,
                company_id=company.id,
                search_query=result.get("search_query", ""),
                raw_data=result,
            )
            db.session.add(search_result)
        
        db.session.commit()


def _run_scrape(
    job_id: str,
    config: ScrapeConfig,
    auto_fetch_emails: bool = False,
    auto_fetch_social: bool = False,
) -> None:
    def on_progress(stage: str, message: str, current: int, total: int) -> None:
        _update_job(
            job_id,
            status="running",
            stage=stage,
            message=message,
            current=current,
            total=total,
        )

    try:
        _update_job(job_id, status="running", stage="starting", message="Launching browser...")
        listings = scrape_google_maps(config, progress_callback=on_progress)
        data = [item.to_dict() for item in listings]
        if not data:
            _update_job(
                job_id,
                status="completed",
                stage="done",
                message="Scrape finished — no listings found.",
                results=[],
                current=0,
                total=0,
            )
            # Update database completion time
            with app.app_context():
                db_job = db.session.get(SearchJob, job_id)
                if db_job:
                    db_job.completed_at = datetime.now(timezone.utc)
                    db.session.commit()
            return

        _update_job(
            job_id,
            results=data,
            current=len(data),
            total=len(data),
            message=f"Scrape complete — {len(data)} businesses found.",
        )
        
        # Save results to database
        _save_results_to_database(job_id, data)

        if auto_fetch_emails or auto_fetch_social:
            _run_post_scrape_enrichment(job_id, data, auto_fetch_emails, auto_fetch_social)
            return

        _update_job(
            job_id,
            status="completed",
            stage="done",
        )
        # Update database completion time
        with app.app_context():
            db_job = db.session.get(SearchJob, job_id)
            if db_job:
                db_job.completed_at = datetime.now(timezone.utc)
                db.session.commit()
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="error",
            message="Scrape failed.",
            error=str(exc),
        )
        # Update database with error
        with app.app_context():
            db_job = db.session.get(SearchJob, job_id)
            if db_job:
                db_job.completed_at = datetime.now(timezone.utc)
                db.session.commit()


@app.route("/")
def index():
    return redirect(url_for("search_history.dashboard"))


@app.route("/new-search")
def new_search():
    return render_template("index.html", default_search_strings=DEFAULT_SEARCH_STRINGS)


@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    payload = request.get_json(silent=True) or {}

    error = _validate_scrape_payload(payload)
    if error:
        return error

    auto_fetch_emails = bool(payload.get("auto_fetch_emails", False))
    auto_fetch_social = bool(payload.get("auto_fetch_social", False))
    config = _config_from_payload(payload)

    job_id = str(uuid.uuid4())

    job = ScrapeJob(
        id=job_id,
        country=config.country,
        max_results=config.max_results,
        search_strings=config.search_strings,
        total=config.max_results,
    )

    with jobs_lock:
        jobs[job_id] = job
    
    # Save to database
    with app.app_context():
        db_job = SearchJob(
            id=job_id,
            status="pending",
            message="Starting scrape...",
            stage="pending",
            current=0,
            total=config.max_results,
            country=config.country,
            state=payload.get("state", ""),
            city=payload.get("city", ""),
            industry=config.industry,
            max_results=config.max_results,
            search_strings=config.search_strings,
            auto_fetch_emails=auto_fetch_emails,
            auto_fetch_social=auto_fetch_social,
        )
        db.session.add(db_job)
        db.session.commit()

    thread = threading.Thread(
        target=_run_scrape,
        args=(job_id, config),
        kwargs={
            "auto_fetch_emails": auto_fetch_emails,
            "auto_fetch_social": auto_fetch_social,
        },
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    show_results = bool(job.results)

    return jsonify(
        {
            "id": job.id,
            "status": job.status,
            "message": job.message,
            "stage": job.stage,
            "current": job.current,
            "total": job.total,
            "results": job.results if show_results else [],
            "error": job.error,
            "country": job.country,
            "max_results": job.max_results,
            "search_strings": job.search_strings,
        }
    )


@app.route("/api/jobs/<job_id>/fetch-emails", methods=["POST"])
def fetch_emails(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            return jsonify({"error": "Job not found."}), 404

        if job.status == "running":
            return jsonify({"error": "A task is already running for this job."}), 400

        if not job.results:
            return jsonify({"error": "No scraped results to enrich."}), 400

        results_copy = [dict(row) for row in job.results]

    thread = threading.Thread(target=_run_email_enrichment_task, args=(job_id, results_copy), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>/fetch-social", methods=["POST"])
def fetch_social(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            return jsonify({"error": "Job not found."}), 404

        if job.status == "running":
            return jsonify({"error": "A task is already running for this job."}), 400

        if not job.results:
            return jsonify({"error": "No scraped results to enrich."}), 400

        results_copy = [dict(row) for row in job.results]

    thread = threading.Thread(target=_run_social_enrichment_task, args=(job_id, results_copy), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>/download/<fmt>")
def download_results(job_id: str, fmt: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job.status != "completed":
        return jsonify({"error": "Results are not ready yet."}), 400

    if not job.results:
        return jsonify({"error": "No results to download."}), 400

    slug = job.country.lower().replace(" ", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if fmt == "json":
        buffer = to_json_bytes_from_dicts(job.results)
        filename = f"{slug}_results_{timestamp}.json"
        return send_file(
            buffer,
            mimetype="application/json",
            as_attachment=True,
            download_name=filename,
        )

    if fmt == "excel":
        buffer = to_excel_bytes_from_dicts(job.results)
        filename = f"{slug}_results_{timestamp}.xlsx"
        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    return jsonify({"error": "Unsupported format. Use json or excel."}), 400


@app.route("/api/scrape/json", methods=["POST"])
def scrape_and_return_json():
    """Synchronous scrape endpoint.

    Accepts the same request body as /api/scrape:
        {
          "country": "India",
          "max_results": 50,
          "search_strings": ["Pharmaceutical importers", ...],
          "auto_fetch_emails": true,
          "auto_fetch_social": true
        }

    Blocks until the scrape (and any requested enrichment) finishes, then
    returns:
        {
          "status": "success",
          "message": "5 businesses found · 3 with emails · 1 with social links",
          "results": [ ... same rows as the "Download JSON" button ... ]
        }

    The message mirrors the summary shown under the results table in the UI,
    with the counts computed dynamically from what was actually found.

    Note: this call is synchronous and can take anywhere from tens of
    seconds to several minutes depending on max_results and whether
    enrichment is requested, since every business page and (optionally)
    every business website is fetched before the response is returned.
    """
    payload = request.get_json(silent=True) or {}

    error = _validate_scrape_payload(payload)
    if error:
        error_body, status_code = error
        error_payload = error_body.get_json()
        return jsonify({"status": "error", "message": error_payload.get("error")}), status_code

    auto_fetch_emails = bool(payload.get("auto_fetch_emails", False))
    auto_fetch_social = bool(payload.get("auto_fetch_social", False))
    config = _config_from_payload(payload)

    try:
        data = _execute_scrape_sync(config, auto_fetch_emails, auto_fetch_social)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify(
        {
            "status": "success",
            "message": _build_summary_message(data),
            "results": data,
        }
    )


if __name__ == "__main__":
    import os

    # The Werkzeug auto-reloader restarts the whole process (killing any
    # in-flight request, including a long-running scrape) whenever it
    # detects a file change — e.g. an editor auto-save. That's convenient
    # while actively coding, but it will kill/500 any /api/scrape/json
    # call that's still running when a save happens. Set
    # FLASK_USE_RELOADER=0 to disable it while you're testing the API
    # (e.g. via Postman) without editing files at the same time.
    use_reloader = os.environ.get("FLASK_USE_RELOADER", "1") != "0"
    if not use_reloader or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_email_scheduler()

    # threaded=True lets the dev server handle multiple requests at once —
    # important here since /api/scrape/json blocks for the duration of a
    # scrape. Without it, the UI (or any other request) would be stuck
    # waiting behind a long-running API call. Note: if you fire multiple
    # scrape requests concurrently, they'll run in parallel (each opening
    # its own browser), which is expected but will be slower and will
    # interleave console output — avoid sending a second request before
    # the first one finishes unless you mean to.
    app.run(debug=True, host="0.0.0.0", port=5050, threaded=True, use_reloader=use_reloader)
