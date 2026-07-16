# Database Setup Instructions

This project now uses PostgreSQL with SQLAlchemy and Flask-Migrate for persistent storage of scrape jobs and results.

## Prerequisites

- PostgreSQL database running (existing leadgen-platform container or your own)
- Python 3.10+
- Virtual environment activated

## Setup Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and customize if needed:

```bash
cp .env.example .env
```

The default configuration in `.env.example` uses the existing PostgreSQL container:
- Host: `localhost`
- Port: `5432`
- User: `postgres`
- Password: `postgres123`
- Database: `leadgen`

If you're using a different PostgreSQL instance, update the `DATABASE_URL` and related variables in `.env`.

### 3. Initialize Database Migrations

```bash
flask db init
```

This creates the `migrations/` directory.

### 4. Create Initial Migration

```bash
flask db migrate -m "Initial migration"
```

This generates the migration script based on your models.

### 5. Apply Migration to Database

```bash
flask db upgrade
```

This creates the tables in PostgreSQL.

### 6. Run the Application

```bash
python app.py
```

The application will now:
- Store scrape jobs in the `scrape_jobs` table
- Store business results in the `business_results` table
- Update job status and progress in the database
- Persist results even after server restart

## Database Schema

### ScrapeJob Table
- `id`: UUID primary key
- `status`: pending, running, completed, failed
- `message`: Progress message
- `stage`: Current stage (starting, searching, extracting, etc.)
- `current`, `total`: Progress counters
- `error`: Error message if failed
- `country`, `max_results`, `search_strings`: Job parameters
- `auto_fetch_emails`, `auto_fetch_social`: Enrichment flags
- `created_at`, `completed_at`: Timestamps
- Relationship with BusinessResult

### BusinessResult Table
- `id`: Auto-increment primary key
- `scrape_job_id`: Foreign key to ScrapeJob
- Business fields: name, address, phone, website, rating, reviews_count, category
- Enrichment fields: email, linkedin, instagram, whatsapp
- Metadata: place_url, search_query, country, industry
- `created_at`: Timestamp

## Useful Commands

### Create New Migration After Model Changes
```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

### Rollback Migration
```bash
flask db downgrade
```

### View Migration History
```bash
flask db history
```

### Reset Database Tables (⚠️ Deletes all data)
```bash
flask db downgrade base
flask db upgrade
```

## Notes

- The in-memory job storage (`jobs` dict in `app.py`) is still used for real-time API responses
- Database provides persistence and historical record of all scrape jobs
- Both storage mechanisms are kept in sync during scrape operations
- Existing scraper and frontend code remain unchanged
- Environment variables are loaded from `.env` file (not committed to git)
