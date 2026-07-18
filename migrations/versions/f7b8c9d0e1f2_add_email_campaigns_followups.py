"""Add email campaigns followups

Revision ID: f7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('subject', sa.String(length=300), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_templates_name'), 'email_templates', ['name'], unique=False)

    op.create_table(
        'email_campaigns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['email_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_campaigns_name'), 'email_campaigns', ['name'], unique=False)
    op.create_index(op.f('ix_email_campaigns_scheduled_at'), 'email_campaigns', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_email_campaigns_status'), 'email_campaigns', ['status'], unique=False)
    op.create_index(op.f('ix_email_campaigns_template_id'), 'email_campaigns', ['template_id'], unique=False)

    op.create_table(
        'email_deliveries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(length=500), nullable=True),
        sa.Column('delivery_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('replied_at', sa.DateTime(), nullable=True),
        sa.Column('rendered_subject', sa.String(length=500), nullable=True),
        sa.Column('rendered_body_html', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['email_campaigns.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['template_id'], ['email_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_deliveries_campaign_id'), 'email_deliveries', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_email_deliveries_company_id'), 'email_deliveries', ['company_id'], unique=False)
    op.create_index(op.f('ix_email_deliveries_delivery_type'), 'email_deliveries', ['delivery_type'], unique=False)
    op.create_index(op.f('ix_email_deliveries_email'), 'email_deliveries', ['email'], unique=False)
    op.create_index(op.f('ix_email_deliveries_replied_at'), 'email_deliveries', ['replied_at'], unique=False)
    op.create_index(op.f('ix_email_deliveries_scheduled_at'), 'email_deliveries', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_email_deliveries_status'), 'email_deliveries', ['status'], unique=False)
    op.create_index(op.f('ix_email_deliveries_template_id'), 'email_deliveries', ['template_id'], unique=False)

    op.create_table(
        'follow_up_automations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('day_number', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivery_id', sa.Integer(), nullable=True),
        sa.Column('skip_reason', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['email_campaigns.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['delivery_id'], ['email_deliveries.id']),
        sa.ForeignKeyConstraint(['template_id'], ['email_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_follow_up_automations_campaign_id'), 'follow_up_automations', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_company_id'), 'follow_up_automations', ['company_id'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_day_number'), 'follow_up_automations', ['day_number'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_scheduled_at'), 'follow_up_automations', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_status'), 'follow_up_automations', ['status'], unique=False)
    op.create_index(op.f('ix_follow_up_automations_template_id'), 'follow_up_automations', ['template_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_follow_up_automations_template_id'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_follow_up_automations_status'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_follow_up_automations_scheduled_at'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_follow_up_automations_day_number'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_follow_up_automations_company_id'), table_name='follow_up_automations')
    op.drop_index(op.f('ix_follow_up_automations_campaign_id'), table_name='follow_up_automations')
    op.drop_table('follow_up_automations')
    op.drop_index(op.f('ix_email_deliveries_template_id'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_status'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_scheduled_at'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_replied_at'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_email'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_delivery_type'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_company_id'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_campaign_id'), table_name='email_deliveries')
    op.drop_table('email_deliveries')
    op.drop_index(op.f('ix_email_campaigns_template_id'), table_name='email_campaigns')
    op.drop_index(op.f('ix_email_campaigns_status'), table_name='email_campaigns')
    op.drop_index(op.f('ix_email_campaigns_scheduled_at'), table_name='email_campaigns')
    op.drop_index(op.f('ix_email_campaigns_name'), table_name='email_campaigns')
    op.drop_table('email_campaigns')
    op.drop_index(op.f('ix_email_templates_name'), table_name='email_templates')
    op.drop_table('email_templates')
