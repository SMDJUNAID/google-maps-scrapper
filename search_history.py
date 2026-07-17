"""Search History Blueprint for managing and viewing search jobs."""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from models import (
    ActivityTimeline,
    CompanyNote,
    CompanyTask,
    Contact,
    EmailCampaign,
    EmailDelivery,
    EmailTemplate,
    FollowUpAutomation,
    SearchJob,
    Company,
    SearchResult,
    Tag,
)
from extensions import db
from sqlalchemy import and_, cast, Date, Float, func, or_
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

TASK_PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']
TASK_STATUSES = ['Open', 'In Progress', 'Blocked', 'Complete']

ACTIVITY_LABELS = {
    'company_created': 'Company created',
    'company_updated': 'Company updated',
    'status_changed': 'Status changed',
    'note_added': 'Note added',
    'note_updated': 'Note updated',
    'note_deleted': 'Note deleted',
    'task_created': 'Task created',
    'task_updated': 'Task updated',
    'task_completed': 'Task completed',
    'task_deleted': 'Task deleted',
    'email_sent': 'Email sent',
    'email_campaign_created': 'Email campaign created',
    'email_campaign_scheduled': 'Email campaign scheduled',
    'follow_up_sent': 'Follow-up sent',
    'lead_replied': 'Lead replied',
    'whatsapp_sent': 'WhatsApp sent',
    'tag_added': 'Tag added',
    'tag_removed': 'Tag removed',
}

EMAIL_TEMPLATE_VARIABLES = ['company_name', 'website', 'country']
FOLLOW_UP_DAYS = [3, 7, 14]


def _current_user():
    return (request.form.get('user') or request.args.get('user') or 'User').strip() or 'User'


def _record_activity(company_id, action_type, description, user='System', metadata=None, commit=False):
    activity = ActivityTimeline(
        company_id=company_id,
        action_type=action_type,
        description=description,
        user=user or 'System',
        metadata_json=metadata or {},
    )
    db.session.add(activity)
    if commit:
        db.session.commit()
    return activity


def _duration_seconds(started_at, completed_at):
    """Return whole seconds between two datetimes, or None when incomplete."""
    if not started_at or not completed_at:
        return None
    return int((completed_at - started_at).total_seconds())


def _job_completed_at(job):
    """Return stored completion time, or infer it from saved result timestamps."""
    if job.completed_at:
        return job.completed_at
    if job.status not in {'completed', 'failed'} or not job.results:
        return None
    result_times = [result.created_at for result in job.results if result.created_at]
    return max(result_times) if result_times else None


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
        'state': company.state,
        'city': company.city,
        'industry': company.industry,
        'lead_status': lead_status,
        'lead_status_badge_class': LEAD_STATUS_BADGE_CLASSES[lead_status],
        'phone': phones[0] if phones else '',
        'email': emails[0] if emails else '',
        'has_whatsapp': bool(_collect_contact_values(contacts, 'whatsapp')),
        'has_linkedin': bool(_collect_contact_values(contacts, 'linkedin')),
        'tags': [tag.to_dict() for tag in sorted(company.tags, key=lambda tag: tag.name.lower())],
        'created_at': _format_datetime(company.created_at),
        'updated_at': _format_datetime(company.updated_at),
    }


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _rating_as_float():
    return cast(func.nullif(Company.rating, ''), Float)


def _first_company_email(company):
    contacts = _latest_contacts_by_type(company.contacts)
    emails = _collect_contact_values(contacts, 'email')
    return emails[0] if emails else ''


def _template_context(company, email=''):
    return {
        'company_name': company.name or '',
        'website': company.website or '',
        'country': company.country or '',
        'email': email or _first_company_email(company),
        'city': company.city or '',
        'state': company.state or '',
    }


def _render_template_text(text, company, email=''):
    rendered = text or ''
    context = _template_context(company, email=email)
    for key, value in context.items():
        rendered = rendered.replace('{{' + key + '}}', value)
        rendered = rendered.replace('{{ ' + key + ' }}', value)
    return rendered


def _campaign_company_query(company_ids):
    return (
        Company.query.options(joinedload(Company.contacts))
        .filter(Company.id.in_(company_ids))
        .order_by(Company.name.asc())
        .all()
    )


def _parse_datetime_local(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _create_delivery(campaign, company, delivery_type='initial', scheduled_at=None, status='Sent'):
    email = _first_company_email(company)
    rendered_subject = _render_template_text(campaign.template.subject, company, email=email)
    rendered_body = _render_template_text(campaign.template.body_html, company, email=email)
    now = datetime.now(timezone.utc)
    delivery = EmailDelivery(
        campaign_id=campaign.id,
        company_id=company.id,
        template_id=campaign.template_id,
        email=email or None,
        delivery_type=delivery_type,
        status='Skipped' if not email else status,
        scheduled_at=scheduled_at,
        sent_at=now if email and status == 'Sent' else None,
        rendered_subject=rendered_subject,
        rendered_body_html=rendered_body,
        error=None if email else 'No email address stored for this company.',
    )
    db.session.add(delivery)
    db.session.flush()
    if email and status == 'Sent':
        _record_activity(
            company.id,
            'email_sent' if delivery_type == 'initial' else 'follow_up_sent',
            f'{delivery_type.replace("_", " ").title()} email recorded for {email}.',
            user=campaign.created_by,
            metadata={'campaign_id': campaign.id, 'delivery_id': delivery.id},
        )
    return delivery


def _schedule_follow_ups(campaign, companies, base_time):
    for company in companies:
        if _normalize_lead_status(company.lead_status) in {'Won', 'Lost'}:
            continue
        if not _first_company_email(company):
            continue
        for day_number in FOLLOW_UP_DAYS:
            db.session.add(
                FollowUpAutomation(
                    campaign_id=campaign.id,
                    company_id=company.id,
                    template_id=campaign.template_id,
                    day_number=day_number,
                    scheduled_at=base_time + timedelta(days=day_number),
                )
            )


def _company_has_replied(company_id, campaign_id=None):
    query = EmailDelivery.query.filter(
        EmailDelivery.company_id == company_id,
        EmailDelivery.replied_at.isnot(None),
    )
    if campaign_id:
        query = query.filter(EmailDelivery.campaign_id == campaign_id)
    return db.session.query(query.exists()).scalar()


def _follow_up_skip_reason(follow_up):
    status = _normalize_lead_status(follow_up.company.lead_status)
    if status in {'Won', 'Lost'}:
        return f'Lead status is {status}.'
    if _company_has_replied(follow_up.company_id, follow_up.campaign_id):
        return 'Lead replied.'
    if not _first_company_email(follow_up.company):
        return 'No email address stored for this company.'
    return None




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
        completed_at = _job_completed_at(job)
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
            'completed_at': completed_at.isoformat() if completed_at else None,
            'duration_seconds': _duration_seconds(job.created_at, completed_at),
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
    """Display companies with CRM filters, pagination, and sorting."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    lead_status_filter = request.args.get('lead_status', '')
    country_filter = request.args.get('country', '')
    state_filter = request.args.get('state', '')
    city_filter = request.args.get('city', '')
    category_filter = request.args.get('category', '')
    industry_filter = request.args.get('industry', '')
    keyword_filter = request.args.get('keyword', '')
    min_rating_filter = request.args.get('min_rating', '')
    website_filter = request.args.get('has_website', '')
    email_filter = request.args.get('has_email', '')
    whatsapp_filter = request.args.get('has_whatsapp', '')
    linkedin_filter = request.args.get('has_linkedin', '')
    tag_filter = request.args.get('tag', type=int)
    sort_filter = request.args.get('sort', '-updated_at,-created_at,name')

    query = Company.query.options(joinedload(Company.contacts), joinedload(Company.tags))
    if lead_status_filter in LEAD_STATUSES:
        query = query.filter(Company.lead_status == lead_status_filter)
    if country_filter:
        query = query.filter(Company.country.ilike(f'%{country_filter}%'))
    if state_filter:
        query = query.filter(Company.state.ilike(f'%{state_filter}%'))
    if city_filter:
        query = query.filter(Company.city.ilike(f'%{city_filter}%'))
    if category_filter:
        query = query.filter(Company.category.ilike(f'%{category_filter}%'))
    if industry_filter:
        query = query.filter(Company.industry.ilike(f'%{industry_filter}%'))
    if keyword_filter:
        query = query.filter(Company.name.ilike(f'%{keyword_filter}%'))
    if min_rating_filter:
        try:
            query = query.filter(_rating_as_float() >= float(min_rating_filter))
        except ValueError:
            min_rating_filter = ''
    if website_filter == 'yes':
        query = query.filter(and_(Company.website.isnot(None), Company.website != ''))
    elif website_filter == 'no':
        query = query.filter(or_(Company.website.is_(None), Company.website == ''))
    if email_filter == 'yes':
        query = query.filter(Company.contacts.any(and_(Contact.email.isnot(None), Contact.email != '')))
    elif email_filter == 'no':
        query = query.filter(~Company.contacts.any(and_(Contact.email.isnot(None), Contact.email != '')))
    if whatsapp_filter == 'yes':
        query = query.filter(Company.contacts.any(and_(Contact.whatsapp.isnot(None), Contact.whatsapp != '')))
    elif whatsapp_filter == 'no':
        query = query.filter(~Company.contacts.any(and_(Contact.whatsapp.isnot(None), Contact.whatsapp != '')))
    if linkedin_filter == 'yes':
        query = query.filter(Company.contacts.any(and_(Contact.linkedin.isnot(None), Contact.linkedin != '')))
    elif linkedin_filter == 'no':
        query = query.filter(~Company.contacts.any(and_(Contact.linkedin.isnot(None), Contact.linkedin != '')))
    if tag_filter:
        query = query.filter(Company.tags.any(Tag.id == tag_filter))

    sort_columns = {
        'name': Company.name,
        'country': Company.country,
        'state': Company.state,
        'city': Company.city,
        'category': Company.category,
        'rating': _rating_as_float(),
        'status': Company.lead_status,
        'created_at': Company.created_at,
        'updated_at': Company.updated_at,
    }
    order_by = []
    for raw_sort in [item.strip() for item in sort_filter.split(',') if item.strip()]:
        descending = raw_sort.startswith('-')
        key = raw_sort[1:] if descending else raw_sort
        column = sort_columns.get(key)
        if column is not None:
            order_by.append(column.desc().nullslast() if descending else column.asc().nullslast())
    if not order_by:
        order_by = [Company.updated_at.desc(), Company.created_at.desc(), Company.name.asc()]
        sort_filter = '-updated_at,-created_at,name'
    query = query.order_by(*order_by)
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
        state_filter=state_filter,
        city_filter=city_filter,
        category_filter=category_filter,
        industry_filter=industry_filter,
        keyword_filter=keyword_filter,
        min_rating_filter=min_rating_filter,
        website_filter=website_filter,
        email_filter=email_filter,
        whatsapp_filter=whatsapp_filter,
        linkedin_filter=linkedin_filter,
        tag_filter=tag_filter,
        sort_filter=sort_filter,
        lead_statuses=LEAD_STATUSES,
        lead_status_counts=_lead_status_counts(),
        tags=Tag.query.order_by(Tag.name.asc()).all(),
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
    completed_at = _job_completed_at(search_job)
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
        'completed_at': completed_at.isoformat() if completed_at else None,
        'duration_seconds': _duration_seconds(search_job.created_at, completed_at),
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
            joinedload(Company.notes),
            joinedload(Company.tasks),
            joinedload(Company.activities),
            joinedload(Company.tags),
            joinedload(Company.email_deliveries).joinedload(EmailDelivery.campaign),
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
    notes = sorted(company.notes, key=lambda note: note.created_at or company.created_at)
    tasks = sorted(
        company.tasks,
        key=lambda task: (
            task.status == 'Complete',
            task.due_date or datetime.max.date(),
            task.created_at or company.created_at,
        ),
    )
    activities = sorted(
        company.activities,
        key=lambda activity: activity.created_at or company.created_at,
        reverse=True,
    )
    email_deliveries = sorted(
        company.email_deliveries,
        key=lambda delivery: delivery.sent_at or delivery.scheduled_at or delivery.created_at,
        reverse=True,
    )

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
        'state': company.state,
        'city': company.city,
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
            completed_at = _job_completed_at(result.search_job)
            job_data['completed_at'] = _format_datetime(completed_at)
            job_data['duration_seconds'] = _duration_seconds(
                result.search_job.created_at, completed_at
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
        notes=[note.to_dict() for note in notes],
        tasks=[task.to_dict() for task in tasks],
        activities=[activity.to_dict() for activity in activities],
        email_deliveries=[
            {
                **delivery.to_dict(),
                'campaign_name': delivery.campaign.name if delivery.campaign else '',
            }
            for delivery in email_deliveries
        ],
        tags=[tag.to_dict() for tag in sorted(company.tags, key=lambda tag: tag.name.lower())],
        all_tags=Tag.query.order_by(Tag.name.asc()).all(),
        search_results=search_results_dicts,
        search_jobs=list(search_jobs_by_id.values()),
        contact_values=contact_values,
        lead_statuses=LEAD_STATUSES,
        lead_status_badge_classes=LEAD_STATUS_BADGE_CLASSES,
        task_priorities=TASK_PRIORITIES,
        task_statuses=TASK_STATUSES,
        activity_labels=ACTIVITY_LABELS,
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

    old_status = _normalize_lead_status(company.lead_status)
    company.lead_status = lead_status
    if old_status != lead_status:
        _record_activity(
            company.id,
            'status_changed',
            f'Status changed from {old_status} to {lead_status}.',
            user=_current_user(),
            metadata={'old_status': old_status, 'new_status': lead_status},
        )
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/company/<int:company_id>/notes', methods=['POST'])
def add_company_note(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        abort(404)

    note_text = request.form.get('note', '').strip()
    user = _current_user()
    if not note_text:
        abort(400, description='Note is required.')

    note = CompanyNote(company_id=company.id, note=note_text, user=user)
    db.session.add(note)
    db.session.flush()
    _record_activity(
        company.id,
        'note_added',
        f'Note added by {user}.',
        user=user,
        metadata={'note_id': note.id},
    )
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/company/<int:company_id>/notes/<int:note_id>', methods=['POST'])
def update_company_note(company_id, note_id):
    note = CompanyNote.query.filter_by(id=note_id, company_id=company_id).first()
    if not note:
        abort(404)

    action = request.form.get('action', 'update')
    user = _current_user()
    if action == 'delete':
        db.session.delete(note)
        _record_activity(
            company_id,
            'note_deleted',
            f'Note deleted by {user}.',
            user=user,
            metadata={'note_id': note_id},
        )
    else:
        note_text = request.form.get('note', '').strip()
        if not note_text:
            abort(400, description='Note is required.')
        note.note = note_text
        note.user = user
        note.edited_at = datetime.now(timezone.utc)
        _record_activity(
            company_id,
            'note_updated',
            f'Note updated by {user}.',
            user=user,
            metadata={'note_id': note.id},
        )
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company_id))


@search_history_bp.route('/company/<int:company_id>/tasks', methods=['POST'])
def add_company_task(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        abort(404)

    title = request.form.get('title', '').strip()
    if not title:
        abort(400, description='Task title is required.')
    priority = request.form.get('priority', 'Medium')
    status = request.form.get('status', 'Open')
    if priority not in TASK_PRIORITIES:
        priority = 'Medium'
    if status not in TASK_STATUSES:
        status = 'Open'

    task = CompanyTask(
        company_id=company.id,
        title=title,
        description=request.form.get('description', '').strip() or None,
        due_date=_parse_date(request.form.get('due_date')),
        priority=priority,
        status=status,
        completed_at=datetime.now(timezone.utc) if status == 'Complete' else None,
    )
    db.session.add(task)
    db.session.flush()
    _record_activity(
        company.id,
        'task_created',
        f'Task created: {task.title}.',
        user=_current_user(),
        metadata={'task_id': task.id, 'priority': task.priority, 'status': task.status},
    )
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/company/<int:company_id>/tasks/<int:task_id>', methods=['POST'])
def update_company_task(company_id, task_id):
    task = CompanyTask.query.filter_by(id=task_id, company_id=company_id).first()
    if not task:
        abort(404)

    action = request.form.get('action', 'update')
    user = _current_user()
    if action == 'delete':
        db.session.delete(task)
        _record_activity(
            company_id,
            'task_deleted',
            f'Task deleted: {task.title}.',
            user=user,
            metadata={'task_id': task_id},
        )
    elif action == 'complete':
        task.status = 'Complete'
        task.completed_at = datetime.now(timezone.utc)
        _record_activity(
            company_id,
            'task_completed',
            f'Task completed: {task.title}.',
            user=user,
            metadata={'task_id': task.id},
        )
    else:
        title = request.form.get('title', '').strip()
        if not title:
            abort(400, description='Task title is required.')
        priority = request.form.get('priority', task.priority)
        status = request.form.get('status', task.status)
        old_status = task.status
        task.title = title
        task.description = request.form.get('description', '').strip() or None
        task.due_date = _parse_date(request.form.get('due_date'))
        task.priority = priority if priority in TASK_PRIORITIES else task.priority
        task.status = status if status in TASK_STATUSES else task.status
        if task.status == 'Complete' and old_status != 'Complete':
            task.completed_at = datetime.now(timezone.utc)
        elif task.status != 'Complete':
            task.completed_at = None
        _record_activity(
            company_id,
            'task_completed' if old_status != 'Complete' and task.status == 'Complete' else 'task_updated',
            f'Task {"completed" if old_status != "Complete" and task.status == "Complete" else "updated"}: {task.title}.',
            user=user,
            metadata={'task_id': task.id, 'status': task.status},
        )
    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company_id))


@search_history_bp.route('/company/<int:company_id>/tags', methods=['POST'])
def update_company_tags(company_id):
    company = Company.query.options(joinedload(Company.tags)).filter_by(id=company_id).first()
    if not company:
        abort(404)

    action = request.form.get('action', 'add')
    user = _current_user()
    if action == 'create':
        name = request.form.get('tag_name', '').strip()
        color = request.form.get('tag_color', '#0f766e').strip() or '#0f766e'
        if not name:
            abort(400, description='Tag name is required.')
        tag = Tag.query.filter(func.lower(Tag.name) == name.lower()).first()
        if not tag:
            tag = Tag(name=name, color=color[:20])
            db.session.add(tag)
            db.session.flush()
        if tag not in company.tags:
            company.tags.append(tag)
            _record_activity(company.id, 'tag_added', f'Tag added: {tag.name}.', user=user, metadata={'tag_id': tag.id})
    elif action == 'remove':
        tag_id = request.form.get('tag_id', type=int)
        tag = Tag.query.get(tag_id) if tag_id else None
        if tag and tag in company.tags:
            company.tags.remove(tag)
            _record_activity(company.id, 'tag_removed', f'Tag removed: {tag.name}.', user=user, metadata={'tag_id': tag.id})
    else:
        tag_id = request.form.get('tag_id', type=int)
        tag = Tag.query.get(tag_id) if tag_id else None
        if tag and tag not in company.tags:
            company.tags.append(tag)
            _record_activity(company.id, 'tag_added', f'Tag added: {tag.name}.', user=user, metadata={'tag_id': tag.id})

    db.session.commit()
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/company/<int:company_id>/email-sent')
def record_email_sent(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        abort(404)
    email = request.args.get('email', '').strip()
    if email:
        _record_activity(
            company.id,
            'email_sent',
            f'Email sent to {email}.',
            user=_current_user(),
            metadata={'email': email},
            commit=True,
        )
        return redirect(f'mailto:{email}')
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/company/<int:company_id>/whatsapp-sent')
def record_whatsapp_sent(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        abort(404)
    whatsapp = request.args.get('whatsapp', '').strip()
    if whatsapp:
        _record_activity(
            company.id,
            'whatsapp_sent',
            f'WhatsApp sent to {whatsapp}.',
            user=_current_user(),
            metadata={'whatsapp': whatsapp},
            commit=True,
        )
        return redirect(whatsapp)
    return redirect(url_for('search_history.company_detail', company_id=company.id))


@search_history_bp.route('/dashboard')
def dashboard():
    """Display CRM and search metrics with Chart.js-ready data."""
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    total_leads = Company.query.count()
    status_counts = dict(
        db.session.query(Company.lead_status, func.count(Company.id))
        .group_by(Company.lead_status)
        .all()
    )
    searches_today = SearchJob.query.filter(SearchJob.created_at >= today_start).count()
    total_searches = SearchJob.query.count()
    leads_by_country = [
        {'label': label or 'Unknown', 'count': count}
        for label, count in db.session.query(Company.country, func.count(Company.id))
        .group_by(Company.country)
        .order_by(func.count(Company.id).desc())
        .limit(12)
        .all()
    ]
    leads_by_category = [
        {'label': label or 'Unknown', 'count': count}
        for label, count in db.session.query(Company.category, func.count(Company.id))
        .group_by(Company.category)
        .order_by(func.count(Company.id).desc())
        .limit(12)
        .all()
    ]

    monthly_counts = {}
    for created_at, count in db.session.query(cast(Company.created_at, Date), func.count(Company.id)).group_by(cast(Company.created_at, Date)).all():
        if created_at:
            key = created_at.strftime('%Y-%m')
            monthly_counts[key] = monthly_counts.get(key, 0) + count
    monthly_growth = [
        {'label': key, 'count': monthly_counts[key]}
        for key in sorted(monthly_counts.keys())[-12:]
    ]

    metrics = {
        'total_leads': total_leads,
        'new_leads': status_counts.get('New', 0),
        'qualified_leads': status_counts.get('Qualified', 0),
        'contacted_leads': status_counts.get('Contacted', 0),
        'won_leads': status_counts.get('Won', 0),
        'lost_leads': status_counts.get('Lost', 0),
        'searches_today': searches_today,
        'total_searches': total_searches,
    }

    return render_template(
        'search_history/dashboard.html',
        metrics=metrics,
        leads_by_country=leads_by_country,
        leads_by_category=leads_by_category,
        monthly_growth=monthly_growth,
        lead_status_counts=_lead_status_counts(),
    )


@search_history_bp.route('/email-templates')
def email_templates():
    templates = EmailTemplate.query.order_by(EmailTemplate.updated_at.desc(), EmailTemplate.created_at.desc()).all()
    return render_template(
        'search_history/email_templates.html',
        templates=[template.to_dict() for template in templates],
        variables=EMAIL_TEMPLATE_VARIABLES,
    )


@search_history_bp.route('/email-templates/new', methods=['GET', 'POST'])
def new_email_template():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        subject = request.form.get('subject', '').strip()
        body_html = request.form.get('body_html', '').strip()
        if not name or not subject or not body_html:
            abort(400, description='Template name, subject, and body are required.')

        template = EmailTemplate(
            name=name,
            subject=subject,
            body_html=body_html,
            created_by=_current_user(),
        )
        db.session.add(template)
        db.session.commit()
        return redirect(url_for('search_history.email_templates'))

    return render_template(
        'search_history/email_template_form.html',
        template=None,
        variables=EMAIL_TEMPLATE_VARIABLES,
        sample_company={
            'company_name': 'Acme Pharma',
            'website': 'https://example.com',
            'country': 'India',
        },
    )


@search_history_bp.route('/email-templates/<int:template_id>/edit', methods=['GET', 'POST'])
def edit_email_template(template_id):
    template = db.session.get(EmailTemplate, template_id)
    if not template:
        abort(404)

    if request.method == 'POST':
        template.name = request.form.get('name', '').strip()
        template.subject = request.form.get('subject', '').strip()
        template.body_html = request.form.get('body_html', '').strip()
        if not template.name or not template.subject or not template.body_html:
            abort(400, description='Template name, subject, and body are required.')
        db.session.commit()
        return redirect(url_for('search_history.email_templates'))

    return render_template(
        'search_history/email_template_form.html',
        template=template.to_dict(),
        variables=EMAIL_TEMPLATE_VARIABLES,
        sample_company={
            'company_name': 'Acme Pharma',
            'website': 'https://example.com',
            'country': 'India',
        },
    )


@search_history_bp.route('/email-templates/<int:template_id>/delete', methods=['POST'])
def delete_email_template(template_id):
    template = db.session.get(EmailTemplate, template_id)
    if not template:
        abort(404)
    if template.campaigns:
        abort(400, description='Templates used by campaigns cannot be deleted.')
    db.session.delete(template)
    db.session.commit()
    return redirect(url_for('search_history.email_templates'))


@search_history_bp.route('/email-campaigns')
def email_campaigns():
    campaigns = (
        EmailCampaign.query.options(joinedload(EmailCampaign.template), joinedload(EmailCampaign.deliveries))
        .order_by(EmailCampaign.created_at.desc())
        .all()
    )
    return render_template(
        'search_history/email_campaigns.html',
        campaigns=campaigns,
        now=datetime.now(timezone.utc),
    )


@search_history_bp.route('/email-campaigns/new', methods=['GET', 'POST'])
def new_email_campaign():
    templates = EmailTemplate.query.order_by(EmailTemplate.name.asc()).all()
    companies = (
        Company.query.options(joinedload(Company.contacts), joinedload(Company.tags))
        .order_by(Company.updated_at.desc(), Company.name.asc())
        .limit(250)
        .all()
    )
    previews = []
    selected_company_ids = [int(value) for value in request.form.getlist('company_ids') if value.isdigit()]
    selected_template_id = request.form.get('template_id', type=int)

    if request.method == 'POST':
        action = request.form.get('action', 'preview')
        template = db.session.get(EmailTemplate, selected_template_id) if selected_template_id else None
        selected_companies = _campaign_company_query(selected_company_ids) if selected_company_ids else []
        if not template:
            abort(400, description='Template is required.')
        if not selected_companies:
            abort(400, description='At least one company is required.')

        for company in selected_companies:
            email = _first_company_email(company)
            previews.append(
                {
                    'company': _company_summary_dict(company),
                    'email': email,
                    'subject': _render_template_text(template.subject, company, email=email),
                    'body_html': _render_template_text(template.body_html, company, email=email),
                }
            )

        if action == 'preview':
            return render_template(
                'search_history/email_campaign_form.html',
                templates=templates,
                companies=companies,
                selected_company_ids=selected_company_ids,
                selected_template_id=selected_template_id,
                previews=previews,
                campaign_name=request.form.get('name', '').strip(),
                scheduled_at=request.form.get('scheduled_at', ''),
            )

        name = request.form.get('name', '').strip() or f'Campaign {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}'
        scheduled_at = _parse_datetime_local(request.form.get('scheduled_at'))
        now = datetime.now(timezone.utc)
        is_scheduled = action == 'schedule'
        if is_scheduled and not scheduled_at:
            abort(400, description='Scheduled campaigns need a scheduled date and time.')

        campaign = EmailCampaign(
            name=name,
            template=template,
            status='Scheduled' if is_scheduled else 'Sent',
            scheduled_at=scheduled_at if is_scheduled else None,
            sent_at=None if is_scheduled else now,
            created_by=_current_user(),
        )
        db.session.add(campaign)
        db.session.flush()

        for company in selected_companies:
            _create_delivery(
                campaign,
                company,
                scheduled_at=scheduled_at if is_scheduled else None,
                status='Scheduled' if is_scheduled else 'Sent',
            )
            _record_activity(
                company.id,
                'email_campaign_scheduled' if is_scheduled else 'email_campaign_created',
                f'Email campaign {"scheduled" if is_scheduled else "sent"}: {campaign.name}.',
                user=campaign.created_by,
                metadata={'campaign_id': campaign.id},
            )

        _schedule_follow_ups(campaign, selected_companies, scheduled_at if is_scheduled else now)
        db.session.commit()
        return redirect(url_for('search_history.email_campaign_detail', campaign_id=campaign.id))

    return render_template(
        'search_history/email_campaign_form.html',
        templates=templates,
        companies=companies,
        selected_company_ids=selected_company_ids,
        selected_template_id=selected_template_id,
        previews=previews,
        campaign_name='',
        scheduled_at='',
    )


@search_history_bp.route('/email-campaigns/<int:campaign_id>')
def email_campaign_detail(campaign_id):
    campaign = (
        EmailCampaign.query.options(
            joinedload(EmailCampaign.template),
            joinedload(EmailCampaign.deliveries).joinedload(EmailDelivery.company),
            joinedload(EmailCampaign.follow_ups).joinedload(FollowUpAutomation.company),
        )
        .filter_by(id=campaign_id)
        .first()
    )
    if not campaign:
        abort(404)

    deliveries = sorted(campaign.deliveries, key=lambda delivery: delivery.created_at, reverse=True)
    follow_ups = sorted(campaign.follow_ups, key=lambda follow_up: follow_up.scheduled_at)
    return render_template(
        'search_history/email_campaign_detail.html',
        campaign=campaign,
        deliveries=deliveries,
        follow_ups=follow_ups,
        now=datetime.now(timezone.utc),
    )


@search_history_bp.route('/email-deliveries/<int:delivery_id>/replied', methods=['POST'])
def mark_email_replied(delivery_id):
    delivery = db.session.get(EmailDelivery, delivery_id)
    if not delivery:
        abort(404)
    delivery.replied_at = datetime.now(timezone.utc)
    delivery.status = 'Replied'
    _record_activity(
        delivery.company_id,
        'lead_replied',
        f'Lead replied to {delivery.email or "an email"}.',
        user=_current_user(),
        metadata={'campaign_id': delivery.campaign_id, 'delivery_id': delivery.id},
    )
    pending_follow_ups = FollowUpAutomation.query.filter_by(
        campaign_id=delivery.campaign_id,
        company_id=delivery.company_id,
        status='Pending',
    ).all()
    for follow_up in pending_follow_ups:
        follow_up.status = 'Cancelled'
        follow_up.skip_reason = 'Lead replied.'
    db.session.commit()
    return redirect(url_for('search_history.email_campaign_detail', campaign_id=delivery.campaign_id))


@search_history_bp.route('/email-campaigns/process-scheduled', methods=['POST'])
def process_scheduled_campaigns():
    now = datetime.now(timezone.utc)
    campaigns = EmailCampaign.query.options(
        joinedload(EmailCampaign.deliveries).joinedload(EmailDelivery.company),
        joinedload(EmailCampaign.template),
    ).filter(
        EmailCampaign.status == 'Scheduled',
        EmailCampaign.scheduled_at <= now,
    ).all()

    sent_count = 0
    for campaign in campaigns:
        for delivery in campaign.deliveries:
            if delivery.status != 'Scheduled':
                continue
            if not delivery.email:
                delivery.status = 'Skipped'
                delivery.error = 'No email address stored for this company.'
                continue
            delivery.status = 'Sent'
            delivery.sent_at = now
            sent_count += 1
            _record_activity(
                delivery.company_id,
                'email_sent',
                f'Scheduled campaign sent to {delivery.email}.',
                user=campaign.created_by,
                metadata={'campaign_id': campaign.id, 'delivery_id': delivery.id},
            )
        campaign.status = 'Sent'
        campaign.sent_at = now

    db.session.commit()
    return redirect(url_for('search_history.email_campaigns', processed=sent_count))


@search_history_bp.route('/follow-ups')
def follow_ups():
    status_filter = request.args.get('status', '')
    query = FollowUpAutomation.query.options(
        joinedload(FollowUpAutomation.company),
        joinedload(FollowUpAutomation.campaign),
    )
    if status_filter:
        query = query.filter(FollowUpAutomation.status == status_filter)
    follow_up_rows = query.order_by(FollowUpAutomation.scheduled_at.asc()).limit(300).all()
    return render_template(
        'search_history/follow_ups.html',
        follow_ups=follow_up_rows,
        status_filter=status_filter,
        now=datetime.now(timezone.utc),
    )


@search_history_bp.route('/follow-ups/process-due', methods=['POST'])
def process_due_follow_ups():
    now = datetime.now(timezone.utc)
    due_follow_ups = (
        FollowUpAutomation.query.options(
            joinedload(FollowUpAutomation.company).joinedload(Company.contacts),
            joinedload(FollowUpAutomation.campaign).joinedload(EmailCampaign.template),
        )
        .filter(FollowUpAutomation.status == 'Pending', FollowUpAutomation.scheduled_at <= now)
        .order_by(FollowUpAutomation.scheduled_at.asc())
        .all()
    )

    for follow_up in due_follow_ups:
        skip_reason = _follow_up_skip_reason(follow_up)
        if skip_reason:
            follow_up.status = 'Skipped'
            follow_up.skip_reason = skip_reason
            continue

        delivery = _create_delivery(
            follow_up.campaign,
            follow_up.company,
            delivery_type=f'follow_up_day_{follow_up.day_number}',
            scheduled_at=follow_up.scheduled_at,
            status='Sent',
        )
        follow_up.status = 'Sent'
        follow_up.sent_at = now
        follow_up.delivery_id = delivery.id

    db.session.commit()
    return redirect(url_for('search_history.follow_ups'))


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
