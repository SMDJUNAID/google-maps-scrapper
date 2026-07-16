"""Database models for storing companies, contacts, search jobs, and results."""

from datetime import datetime, timezone
from extensions import db


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
    industry = db.Column(db.String(200), nullable=True)
    lead_status = db.Column(db.String(50), nullable=False, default='New', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship with contacts
    contacts = db.relationship('Contact', backref='company', lazy=True, cascade='all, delete-orphan')
    # Relationship with search results
    search_results = db.relationship('SearchResult', backref='company', lazy=True, cascade='all, delete-orphan')

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
