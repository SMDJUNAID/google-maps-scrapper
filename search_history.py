"""Search History Blueprint for managing and viewing search jobs."""

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from models import SearchJob, Company, SearchResult
from extensions import db
from sqlalchemy import func
from sqlalchemy.orm import joinedload

search_history_bp = Blueprint('search_history', __name__, url_prefix='/search-history')

LEAD_STATUSES = [
    'New',
    'Qualified',
    'Contacted',
    'Interested',
    'Meeting Scheduled',
    'Proposal Sent',
    'Negotiation',
    'Won',
    'Lost',
]

LEAD_STATUS_BADGE_CLASSES = {
    'New': 'secondary',
    'Qualified': 'primary',
    'Contacted': 'info',
    'Interested': 'warning',
    'Meeting Scheduled': 'teal',
    'Proposal Sent': 'dark',
    'Negotiation': 'orange',
    'Won': 'success',
    'Lost': 'danger',
}


def _duration_seconds(started_at, completed_at):
    """Return whole seconds between two datetimes, or None when incomplete."""
    if not started_at or not completed_at:
        return None
    return int((completed_at - started_at).total_seconds())


def _format_datetime(value):
    return value.isoformat() if value else None


def _normalize_lead_status(value):
    return value if value in LEAD_STATUSES else 'New'


def _lead_status_counts():
    raw_counts = dict(
        db.session.query(Company.lead_status, func.count(Company.id))
        .group_by(Company.lead_status)
        .all()
    )
    return [
        {
            'status': status,
            'count': raw_counts.get(status, 0),
            'badge_class': LEAD_STATUS_BADGE_CLASSES[status],
        }
        for status in LEAD_STATUSES
    ]


def _split_stored_values(value):
    """Split comma-separated contact fields while preserving single values."""
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value).replace("\n", ",").split(",")

    seen = set()
    values = []
    for item in raw_items:
        cleaned = str(item).strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            values.append(cleaned)
    return values


def _collect_contact_values(contacts, field_name):
    values = []
    seen = set()
    for contact in contacts:
        for item in _split_stored_values(getattr(contact, field_name, None)):
            key = item.lower()
            if key not in seen:
                seen.add(key)
                values.append(item)
    return values


def _collect_raw_values(search_results, field_name):
    values = []
    seen = set()
    for result in search_results:
        raw_data = result.raw_data or {}
        for item in _split_stored_values(raw_data.get(field_name)):
            key = item.lower()
            if key not in seen:
                seen.add(key)
                values.append(item)
    return values


def _latest_contacts_by_type(contacts):
    """Return only the newest contact row for each contact type."""
    latest = {}
    for contact in contacts:
        contact_type = contact.contact_type or 'general'
        current = latest.get(contact_type)
        contact_time = contact.updated_at or contact.created_at
        current_time = (current.updated_at or current.created_at) if current else None
        if (
            not current
            or (contact_time and (not current_time or contact_time > current_time))
            or (contact_time == current_time and contact.id > current.id)
        ):
            latest[contact_type] = contact
    return sorted(latest.values(), key=lambda contact: contact.contact_type or 'general')


def _company_summary_dict(company):
    contacts = _latest_contacts_by_type(company.contacts)
    phones = _collect_contact_values(contacts, 'phone')
    emails = _collect_contact_values(contacts, 'email')
    lead_status = _normalize_lead_status(company.lead_status)
    return {
        'id': company.id,
        'name': company.name,
        'address': company.address,
        'website': company.website,
        'category': company.category,
        'rating': company.rating,
        'reviews_count': company.reviews_count,
        'place_url': company.place_url,
        'country': company.country,
        'industry': company.industry,
        'lead_status': lead_status,
        'lead_status_badge_class': LEAD_STATUS_BADGE_CLASSES[lead_status],
        'phone': phones[0] if phones else '',
        'email': emails[0] if emails else '',
        'created_at': _format_datetime(company.created_at),
        'updated_at': _format_datetime(company.updated_at),
    }


@search_history_bp.route('/')
def index():
    """Display search history with pagination and filters."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get filter parameters
    status_filter = request.args.get('status', '')
    lead_status_filter = request.args.get('lead_status', '')
    country_filter = request.args.get('country', '')
    industry_filter = request.args.get('industry', '')
    keyword_filter = request.args.get('keyword', '')

    if lead_status_filter in LEAD_STATUSES:
        return redirect(url_for('search_history.companies', lead_status=lead_status_filter))
    
    # Build query
    query = SearchJob.query
    
    if status_filter:
        query = query.filter(SearchJob.status == status_filter)
    if lead_status_filter in LEAD_STATUSES:
        query = (
            query.join(SearchResult, SearchJob.id == SearchResult.search_job_id)
            .join(Company, Company.id == SearchResult.company_id)
            .filter(Company.lead_status == lead_status_filter)
            .distinct()
        )
    if country_filter:
        query = query.filter(SearchJob.country.ilike(f'%{country_filter}%'))
    if industry_filter:
        query = query.filter(SearchJob.industry.ilike(f'%{industry_filter}%'))
    # Skip keyword filter for now due to JSON field compatibility issues
    
    # Order by created_at descending
    query = query.order_by(SearchJob.created_at.desc())
    
    # Eager load results relationship to avoid lazy loading issues
    query = query.options(joinedload(SearchJob.results))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    search_jobs = pagination.items
    
    # Convert to dicts to avoid SQLAlchemy session issues
    search_jobs_dicts = []
    for job in search_jobs:
        job_dict = {
            'id': job.id,
            'status': job.status,
            'message': job.message,
            'stage': job.stage,
            'current': job.current,
            'total': job.total,
            'error': job.error,
            'country': job.country,
            'state': job.state,
            'city': job.city,
            'industry': job.industry,
            'max_results': job.max_results,
            'search_strings': job.search_strings,
            'auto_fetch_emails': job.auto_fetch_emails,
            'auto_fetch_social': job.auto_fetch_social,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'duration_seconds': _duration_seconds(job.created_at, job.completed_at),
        }
        # Add computed fields
        job_dict['leads_found'] = len(job.results) if job.results else 0
        job_dict['search_keyword'] = job.search_strings[0] if job.search_strings and isinstance(job.search_strings, list) and len(job.search_strings) > 0 else str(job.search_strings) if job.search_strings else ""
        search_jobs_dicts.append(job_dict)
    
    # Get unique values for filters
    countries = db.session.query(SearchJob.country).distinct().all()
    industries = db.session.query(SearchJob.industry).filter(SearchJob.industry.isnot(None)).distinct().all()
    
    # Convert pagination info to simple dict
    pagination_dict = {
        'page': pagination.page,
        'pages': pagination.pages,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'prev_num': pagination.prev_num,
        'next_num': pagination.next_num,
    }
    
    return render_template(
        'search_history/index.html',
        search_jobs=search_jobs_dicts,
        pagination=pagination_dict,
        status_filter=status_filter,
        lead_status_filter=lead_status_filter,
        lead_statuses=LEAD_STATUSES,
        lead_status_counts=_lead_status_counts(),
        lead_status_badge_classes=LEAD_STATUS_BADGE_CLASSES,
        country_filter=country_filter,
        industry_filter=industry_filter,
        keyword_filter=keyword_filter,
        countries=[c[0] for c in countries if c[0]],
        industries=[i[0] for i in industries if i[0]],
    )


@search_history_bp.route('/companies')
def companies():
    """Display companies, optionally filtered by CRM lead status."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    lead_status_filter = request.args.get('lead_status', '')
    country_filter = request.args.get('country', '')
    industry_filter = request.args.get('industry', '')
    keyword_filter = request.args.get('keyword', '')

    query = Company.query.options(joinedload(Company.contacts))
    if lead_status_filter in LEAD_STATUSES:
        query = query.filter(Company.lead_status == lead_status_filter)
    if country_filter:
        query = query.filter(Company.country.ilike(f'%{country_filter}%'))
    if industry_filter:
        query = query.filter(Company.industry.ilike(f'%{industry_filter}%'))
    if keyword_filter:
        query = query.filter(Company.name.ilike(f'%{keyword_filter}%'))

    query = query.order_by(Company.updated_at.desc(), Company.created_at.desc(), Company.name.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    companies_dicts = [_company_summary_dict(company) for company in pagination.items]
    pagination_dict = {
        'page': pagination.page,
        'pages': pagination.pages,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'prev_num': pagination.prev_num,
        'next_num': pagination.next_num,
        'total': pagination.total,
    }

    return render_template(
        'search_history/companies.html',
        companies=companies_dicts,
        pagination=pagination_dict,
        lead_status_filter=lead_status_filter if lead_status_filter in LEAD_STATUSES else '',
        country_filter=country_filter,
        industry_filter=industry_filter,
        keyword_filter=keyword_filter,
        lead_statuses=LEAD_STATUSES,
        lead_status_counts=_lead_status_counts(),
    )


@search_history_bp.route('/<search_job_id>')
def detail(search_job_id):
    """Display details of a specific search job and its companies."""
    search_job = db.session.get(SearchJob, search_job_id)
    if not search_job:
        from flask import abort
        abort(404)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get search results for this job
    query = SearchResult.query.filter_by(search_job_id=search_job_id)
    query = query.order_by(SearchResult.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    search_results = pagination.items
    
    # Get companies for these results
    company_ids = [r.company_id for r in search_results if r.company_id]
    companies = Company.query.filter(Company.id.in_(company_ids)).all()
    
    # Convert to dicts to avoid SQLAlchemy session issues
    search_job_dict = {
        'id': search_job.id,
        'status': search_job.status,
        'message': search_job.message,
        'stage': search_job.stage,
        'current': search_job.current,
        'total': search_job.total,
        'error': search_job.error,
        'country': search_job.country,
        'state': search_job.state,
        'city': search_job.city,
        'industry': search_job.industry,
        'max_results': search_job.max_results,
        'search_strings': search_job.search_strings,
        'auto_fetch_emails': search_job.auto_fetch_emails,
        'auto_fetch_social': search_job.auto_fetch_social,
        'created_at': search_job.created_at.isoformat() if search_job.created_at else None,
        'completed_at': search_job.completed_at.isoformat() if search_job.completed_at else None,
        'duration_seconds': _duration_seconds(search_job.created_at, search_job.completed_at),
        'leads_found': len(search_job.results) if search_job.results else 0,
        'search_keyword': search_job.search_strings[0] if search_job.search_strings and isinstance(search_job.search_strings, list) and len(search_job.search_strings) > 0 else str(search_job.search_strings) if search_job.search_strings else "",
    }
    
    companies_dict = {}
    for company in companies:
        latest_contacts = _latest_contacts_by_type(company.contacts)
        companies_dict[company.id] = {
            'id': company.id,
            'name': company.name,
            'address': company.address,
            'website': company.website,
            'category': company.category,
            'rating': company.rating,
            'reviews_count': company.reviews_count,
            'place_url': company.place_url,
            'country': company.country,
            'industry': company.industry,
            'lead_status': _normalize_lead_status(company.lead_status),
            'lead_status_badge_class': LEAD_STATUS_BADGE_CLASSES[
                _normalize_lead_status(company.lead_status)
            ],
            'contacts': [
                {'phone': c.phone, 'email': c.email, 'linkedin': c.linkedin, 'instagram': c.instagram, 'whatsapp': c.whatsapp}
                for c in latest_contacts
            ] if latest_contacts else []
        }
    
    search_results_dicts = []
    for result in search_results:
        search_results_dicts.append({
            'id': result.id,
            'search_job_id': result.search_job_id,
            'company_id': result.company_id,
            'search_query': result.search_query,
            'raw_data': result.raw_data,
            'created_at': result.created_at.isoformat() if result.created_at else None,
        })
    
    # Convert pagination info to simple dict
    pagination_dict = {
        'page': pagination.page,
        'pages': pagination.pages,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'prev_num': pagination.prev_num,
        'next_num': pagination.next_num,
    }
    
    return render_template(
        'search_history/detail.html',
        search_job=search_job_dict,
        search_results=search_results_dicts,
        companies_dict=companies_dict,
        pagination=pagination_dict,
    )


@search_history_bp.route('/company/<int:company_id>')
def company_detail(company_id):
    """Display all stored details for a single company."""
    company = (
        Company.query.options(
            joinedload(Company.contacts),
            joinedload(Company.search_results).joinedload(SearchResult.search_job),
        )
        .filter(Company.id == company_id)
        .first()
    )
    if not company:
        abort(404)

    search_results = sorted(
        company.search_results,
        key=lambda result: result.created_at or company.created_at,
        reverse=True,
    )
    contacts = _latest_contacts_by_type(company.contacts)

    company_dict = {
        'id': company.id,
        'name': company.name,
        'address': company.address,
        'website': company.website,
        'category': company.category,
        'rating': company.rating,
        'reviews_count': company.reviews_count,
        'place_url': company.place_url,
        'country': company.country,
        'industry': company.industry,
        'lead_status': _normalize_lead_status(company.lead_status),
        'lead_status_badge_class': LEAD_STATUS_BADGE_CLASSES[
            _normalize_lead_status(company.lead_status)
        ],
        'created_at': _format_datetime(company.created_at),
        'updated_at': _format_datetime(company.updated_at),
    }

    contacts_dicts = [
        {
            'id': contact.id,
            'company_id': contact.company_id,
            'phone': contact.phone,
            'email': contact.email,
            'linkedin': contact.linkedin,
            'instagram': contact.instagram,
            'whatsapp': contact.whatsapp,
            'contact_type': contact.contact_type,
            'created_at': _format_datetime(contact.created_at),
            'updated_at': _format_datetime(contact.updated_at),
        }
        for contact in contacts
    ]

    search_results_dicts = [
        {
            'id': result.id,
            'search_job_id': result.search_job_id,
            'company_id': result.company_id,
            'search_query': result.search_query,
            'raw_data': result.raw_data or {},
            'created_at': _format_datetime(result.created_at),
            'search_job': result.search_job.to_dict() if result.search_job else None,
        }
        for result in search_results
    ]

    search_jobs_by_id = {}
    for result in search_results:
        if result.search_job and result.search_job.id not in search_jobs_by_id:
            job_data = result.search_job.to_dict()
            job_data['duration_seconds'] = _duration_seconds(
                result.search_job.created_at, result.search_job.completed_at
            )
            search_jobs_by_id[result.search_job.id] = job_data

    contact_values = {
        'phones': _collect_contact_values(contacts, 'phone'),
        'emails': _collect_contact_values(contacts, 'email'),
        'whatsapp': _collect_contact_values(contacts, 'whatsapp'),
        'linkedin': _collect_contact_values(contacts, 'linkedin'),
        'instagram': _collect_contact_values(contacts, 'instagram'),
        'facebook': _collect_raw_values(search_results, 'facebook'),
    }

    return render_template(
        'search_history/company_detail.html',
        company=company_dict,
        contacts=contacts_dicts,
        search_results=search_results_dicts,
        search_jobs=list(search_jobs_by_id.values()),
        contact_values=contact_values,
        lead_statuses=LEAD_STATUSES,
        lead_status_badge_classes=LEAD_STATUS_BADGE_CLASSES,
    )


@search_history_bp.route('/company/<int:company_id>/status', methods=['POST'])
def update_company_status(company_id):
    """Update CRM lead status for a company."""
    company = db.session.get(Company, company_id)
    if not company:
        abort(404)

    lead_status = request.form.get('lead_status', '').strip()
    if lead_status not in LEAD_STATUSES:
        abort(400, description='Invalid lead status.')

    company.lead_status = lead_status
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/api/search-jobs')
def api_search_jobs():
    """API endpoint for search jobs with filtering."""
    status_filter = request.args.get('status', '')
    country_filter = request.args.get('country', '')
    industry_filter = request.args.get('industry', '')
    keyword_filter = request.args.get('keyword', '')
    
    query = SearchJob.query
    
    if status_filter:
        query = query.filter(SearchJob.status == status_filter)
    if country_filter:
        query = query.filter(SearchJob.country.ilike(f'%{country_filter}%'))
    if industry_filter:
        query = query.filter(SearchJob.industry.ilike(f'%{industry_filter}%'))
    # Skip keyword filter for now due to JSON field compatibility issues
    
    query = query.order_by(SearchJob.created_at.desc())
    
    search_jobs = query.limit(100).all()
    
    return jsonify({
        'search_jobs': [job.to_dict() for job in search_jobs]
    })
