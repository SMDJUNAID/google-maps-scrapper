"""Add lead status to companies

Revision ID: c3f4d5e6a7b8
Revises: 7f08754e2120
Create Date: 2026-07-16 21:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f4d5e6a7b8'
down_revision = '7f08754e2120'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('lead_status', sa.String(length=50), nullable=False, server_default='New')
        )
        batch_op.create_index(batch_op.f('ix_companies_lead_status'), ['lead_status'], unique=False)

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.alter_column('lead_status', server_default=None)


def downgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companies_lead_status'))
        batch_op.drop_column('lead_status')
