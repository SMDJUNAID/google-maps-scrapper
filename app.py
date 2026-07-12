#!/usr/bin/env python3
"""Web UI for Google Maps business listing scraper."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

from scraper.email_finder import enrich_results_with_emails
from scraper.export import to_excel_bytes_from_dicts, to_json_bytes_from_dicts
from scraper.maps_scraper import scrape_google_maps
from scraper.models import ScrapeConfig
from scraper.social_finder import enrich_results_with_social

app = Flask(__name__)

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


def _update_job(job_id: str, **kwargs: Any) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)


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
        current = results
        if auto_fetch_emails:
            current = _run_email_enrichment(job_id, current)
        if auto_fetch_social:
            _run_social_enrichment(job_id, current)
            return
        if auto_fetch_emails:
            _update_job(job_id, status="completed", stage="done")
            return
    except Exception:
        return


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
            return

        _update_job(
            job_id,
            results=data,
            current=len(data),
            total=len(data),
            message=f"Scrape complete — {len(data)} businesses found.",
        )

        if auto_fetch_emails or auto_fetch_social:
            _run_post_scrape_enrichment(job_id, data, auto_fetch_emails, auto_fetch_social)
            return

        _update_job(
            job_id,
            status="completed",
            stage="done",
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="error",
            message="Scrape failed.",
            error=str(exc),
        )


@app.route("/")
def index():
    return render_template("index.html", default_search_strings=DEFAULT_SEARCH_STRINGS)


@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    payload = request.get_json(silent=True) or {}

    country = (payload.get("country") or "").strip()
    max_results = payload.get("max_results", 100)
    search_strings = payload.get("search_strings") or []
    auto_fetch_emails = bool(payload.get("auto_fetch_emails", False))
    auto_fetch_social = bool(payload.get("auto_fetch_social", False))

    if not country:
        return jsonify({"error": "Country is required."}), 400

    if not isinstance(max_results, int) or max_results < 1:
        return jsonify({"error": "Max results must be a positive integer."}), 400

    cleaned_strings = [s.strip() for s in search_strings if isinstance(s, str) and s.strip()]
    if not cleaned_strings:
        return jsonify({"error": "At least one search string is required."}), 400

    job_id = str(uuid.uuid4())
    industry_label = ", ".join(cleaned_strings[:3])
    if len(cleaned_strings) > 3:
        industry_label += f" (+{len(cleaned_strings) - 3} more)"

    config = ScrapeConfig(
        country=country,
        industry=industry_label,
        max_results=max_results,
        search_strings=cleaned_strings,
        headless=True,
    )

    job = ScrapeJob(
        id=job_id,
        country=country,
        max_results=max_results,
        search_strings=cleaned_strings,
        total=max_results,
    )

    with jobs_lock:
        jobs[job_id] = job

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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
