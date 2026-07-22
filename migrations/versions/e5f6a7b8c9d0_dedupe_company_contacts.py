"""Dedupe company contacts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-16 23:05:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE contacts SET contact_type = 'general' WHERE contact_type IS NULL OR contact_type = ''")
    op.execute(
        """
        DELETE FROM contacts
        WHERE id NOT IN (
            SELECT id
            FROM (
                SELECT DISTINCT ON (company_id, contact_type)
                    id,
                    company_id,
                    contact_type
                FROM contacts
                ORDER BY company_id, contact_type, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            ) latest_contacts
        )
        """
    )
    op.create_unique_constraint(
        'uq_contacts_company_contact_type',
        'contacts',
        ['company_id', 'contact_type'],
    )


def downgrade():
    op.drop_constraint('uq_contacts_company_contact_type', 'contacts', type_='unique')
