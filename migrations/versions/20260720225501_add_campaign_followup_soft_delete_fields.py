"""Add campaign followup soft delete fields

Revision ID: 20260720225501
Revises: f7b8c9d0e1f2
Create Date: 2026-07-20 22:55:01.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260720225501'
down_revision = 'f7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('email_campaigns', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('email_campaigns', sa.Column('follow_up_days', sa.String(length=100), nullable=True))
    op.add_column('follow_up_automations', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_email_campaigns_deleted_at'), 'email_campaigns', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_deleted_at'), 'follow_up_automations', ['deleted_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_follow_up_automations_deleted_at'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_email_campaigns_deleted_at'), table_name='email_campaigns')
    op.drop_column('follow_up_automations', 'deleted_at')
    op.drop_column('email_campaigns', 'follow_up_days')
    op.drop_column('email_campaigns', 'deleted_at')
