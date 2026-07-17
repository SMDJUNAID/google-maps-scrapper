"""Database models for storing companies, contacts, search jobs, and results."""

from datetime import datetime, timezone
from extensions import db


company_tags = db.Table(
    'company_tags',
    db.Column('company_id', db.Integer, db.ForeignKey('companies.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False),
)


class Company(db.Model):
    """Model for storing company information."""
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(500), nullable=False, index=True)
    address = db.Column(db.Text, nullable=True)
    website = db.Column(db.String(500), nullable=True, index=True, unique=True)
    category = db.Column(db.String(200), nullable=True)
    rating = db.Column(db.String(20), nullable=True)
    reviews_count = db.Column(db.String(50), nullable=True)
    place_url = db.Column(db.Text, nullable=True, unique=True)
    country = db.Column(db.String(100), nullable=True, index=True)
    state = db.Column(db.String(100), nullable=True, index=True)
    city = db.Column(db.String(100), nullable=True, index=True)
    industry = db.Column(db.String(200), nullable=True)
    lead_status = db.Column(db.String(50), nullable=False, default='New', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship with contacts
    contacts = db.relationship('Contact', backref='company', lazy=True, cascade='all, delete-orphan')
    # Relationship with search results
    search_results = db.relationship('SearchResult', backref='company', lazy=True, cascade='all, delete-orphan')
    notes = db.relationship('CompanyNote', backref='company', lazy=True, cascade='all, delete-orphan')
    tasks = db.relationship('CompanyTask', backref='company', lazy=True, cascade='all, delete-orphan')
    activities = db.relationship('ActivityTimeline', backref='company', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=company_tags, back_populates='companies')
    email_deliveries = db.relationship('EmailDelivery', backref='company', lazy=True, cascade='all, delete-orphan')
    follow_ups = db.relationship('FollowUpAutomation', backref='company', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'website': self.website,
            'category': self.category,
            'rating': self.rating,
            'reviews_count': self.reviews_count,
            'place_url': self.place_url,
            'country': self.country,
            'state': self.state,
            'city': self.city,
            'industry': self.industry,
            'lead_status': self.lead_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Contact(db.Model):
    """Model for storing contact information for companies."""
    __tablename__ = 'contacts'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'contact_type', name='uq_contacts_company_contact_type'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    phone = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(500), nullable=True, index=True)
    linkedin = db.Column(db.Text, nullable=True)
    instagram = db.Column(db.Text, nullable=True)
    whatsapp = db.Column(db.Text, nullable=True)
    contact_type = db.Column(db.String(50), default='general')  # general, sales, support, etc.
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'company_id': self.company_id,
            'phone': self.phone,
            'email': self.email,
            'linkedin': self.linkedin,
            'instagram': self.instagram,
            'whatsapp': self.whatsapp,
            'contact_type': self.contact_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SearchJob(db.Model):
    """Model for storing search/scrape job information."""
    __tablename__ = 'search_jobs'

    id = db.Column(db.String(36), primary_key=True)
    status = db.Column(db.String(50), nullable=False, default='pending', index=True)
    message = db.Column(db.String(500), nullable=False, default='Starting scrape...')
    stage = db.Column(db.String(50), nullable=False, default='pending')
    current = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    error = db.Column(db.Text, nullable=True)
    country = db.Column(db.String(100), nullable=False, index=True)
    state = db.Column(db.String(100), nullable=True, index=True)
    city = db.Column(db.String(100), nullable=True, index=True)
    industry = db.Column(db.String(200), nullable=True, index=True)
    max_results = db.Column(db.Integer, nullable=False)
    search_strings = db.Column(db.JSON, nullable=False)
    auto_fetch_emails = db.Column(db.Boolean, default=False)
    auto_fetch_social = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationship with results
    results = db.relationship('SearchResult', backref='search_job', lazy=True, cascade='all, delete-orphan')

    @property
    def leads_found(self):
        """Get the number of leads found for this search."""
        if self.results:
            return len(self.results)
        return 0

    @property
    def search_keyword(self):
        """Get the primary search keyword."""
        if self.search_strings:
            if isinstance(self.search_strings, list) and len(self.search_strings) > 0:
                return self.search_strings[0]
            elif isinstance(self.search_strings, dict):
                # Handle case where JSON is stored as dict
                return str(self.search_strings)
        return ""

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'status': self.status,
            'message': self.message,
            'stage': self.stage,
            'current': self.current,
            'total': self.total,
            'error': self.error,
            'country': self.country,
            'state': self.state,
            'city': self.city,
            'industry': self.industry,
            'max_results': self.max_results,
            'search_strings': self.search_strings,
            'auto_fetch_emails': self.auto_fetch_emails,
            'auto_fetch_social': self.auto_fetch_social,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'leads_found': self.leads_found,
            'search_keyword': self.search_keyword,
        }


class SearchResult(db.Model):
    """Model for storing individual search results."""
    __tablename__ = 'search_results'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    search_job_id = db.Column(db.String(36), db.ForeignKey('search_jobs.id'), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    search_query = db.Column(db.String(500), nullable=True)
    raw_data = db.Column(db.JSON, nullable=True)  # Store original scraped data
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'search_job_id': self.search_job_id,
            'company_id': self.company_id,
            'search_query': self.search_query,
            'raw_data': self.raw_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CompanyNote(db.Model):
    """Free-form notes attached to a company."""
    __tablename__ = 'company_notes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    note = db.Column(db.Text, nullable=False)
    user = db.Column(db.String(120), nullable=False, default='User')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    edited_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'note': self.note,
            'user': self.user,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'edited_at': self.edited_at.isoformat() if self.edited_at else None,
        }


class CompanyTask(db.Model):
    """Actionable task attached to a company."""
    __tablename__ = 'company_tasks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True, index=True)
    priority = db.Column(db.String(50), nullable=False, default='Medium', index=True)
    status = db.Column(db.String(50), nullable=False, default='Open', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_overdue(self):
        if not self.due_date or self.status == 'Complete':
            return False
        return self.due_date < datetime.now(timezone.utc).date()

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'priority': self.priority,
            'status': self.status,
            'is_overdue': self.is_overdue,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class ActivityTimeline(db.Model):
    """Chronological log of important company actions."""
    __tablename__ = 'activity_timeline'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    action_type = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False)
    user = db.Column(db.String(120), nullable=False, default='System')
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'action_type': self.action_type,
            'description': self.description,
            'user': self.user,
            'metadata': self.metadata_json or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EmailTemplate(db.Model):
    """Reusable rich-text email template with merge variables."""
    __tablename__ = 'email_templates'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    subject = db.Column(db.String(300), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120), nullable=False, default='User')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    campaigns = db.relationship('EmailCampaign', backref='template', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'subject': self.subject,
            'body_html': self.body_html,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class EmailCampaign(db.Model):
    """Batch email campaign sent or scheduled for selected companies."""
    __tablename__ = 'email_campaigns'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('email_templates.id'), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default='Draft', index=True)
    scheduled_at = db.Column(db.DateTime, nullable=True, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(120), nullable=False, default='User')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    deliveries = db.relationship('EmailDelivery', backref='campaign', lazy=True, cascade='all, delete-orphan')
    follow_ups = db.relationship('FollowUpAutomation', backref='campaign', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'template_id': self.template_id,
            'status': self.status,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class EmailDelivery(db.Model):
    """Per-company delivery history for campaign and follow-up emails."""
    __tablename__ = 'email_deliveries'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('email_campaigns.id'), nullable=True, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('email_templates.id'), nullable=True, index=True)
    email = db.Column(db.String(500), nullable=True, index=True)
    delivery_type = db.Column(db.String(80), nullable=False, default='initial', index=True)
    status = db.Column(db.String(50), nullable=False, default='Pending', index=True)
    scheduled_at = db.Column(db.DateTime, nullable=True, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True, index=True)
    rendered_subject = db.Column(db.String(500), nullable=True)
    rendered_body_html = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    template = db.relationship('EmailTemplate', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'company_id': self.company_id,
            'template_id': self.template_id,
            'email': self.email,
            'delivery_type': self.delivery_type,
            'status': self.status,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'replied_at': self.replied_at.isoformat() if self.replied_at else None,
            'rendered_subject': self.rendered_subject,
            'rendered_body_html': self.rendered_body_html,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class FollowUpAutomation(db.Model):
    """Scheduled follow-up email for a campaign recipient."""
    __tablename__ = 'follow_up_automations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('email_campaigns.id'), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('email_templates.id'), nullable=False, index=True)
    day_number = db.Column(db.Integer, nullable=False, index=True)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default='Pending', index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('email_deliveries.id'), nullable=True)
    skip_reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    template = db.relationship('EmailTemplate', lazy=True)
    delivery = db.relationship('EmailDelivery', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'company_id': self.company_id,
            'template_id': self.template_id,
            'day_number': self.day_number,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivery_id': self.delivery_id,
            'skip_reason': self.skip_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Tag(db.Model):
    """Custom tag that can be applied to many companies."""
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    color = db.Column(db.String(20), nullable=False, default='#0f766e')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    companies = db.relationship('Company', secondary=company_tags, back_populates='tags')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
