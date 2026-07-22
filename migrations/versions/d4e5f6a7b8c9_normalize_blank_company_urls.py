"""Normalize blank company URLs

Revision ID: d4e5f6a7b8c9
Revises: c3f4d5e6a7b8
Create Date: 2026-07-16 22:40:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3f4d5e6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE companies SET website = NULL WHERE website = ''")
    op.execute("UPDATE companies SET place_url = NULL WHERE place_url = ''")


def downgrade():
    pass
