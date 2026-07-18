"""Add notes tasks timeline tags

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('state', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.create_index(batch_op.f('ix_companies_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_companies_city'), ['city'], unique=False)

    op.create_table(
        'company_notes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('user', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('edited_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_notes_company_id'), 'company_notes', ['company_id'], unique=False)
    op.create_index(op.f('ix_company_notes_created_at'), 'company_notes', ['created_at'], unique=False)

    op.create_table(
        'company_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('priority', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_tasks_company_id'), 'company_tasks', ['company_id'], unique=False)
    op.create_index(op.f('ix_company_tasks_due_date'), 'company_tasks', ['due_date'], unique=False)
    op.create_index(op.f('ix_company_tasks_priority'), 'company_tasks', ['priority'], unique=False)
    op.create_index(op.f('ix_company_tasks_status'), 'company_tasks', ['status'], unique=False)

    op.create_table(
        'activity_timeline',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=80), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('user', sa.String(length=120), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_activity_timeline_action_type'), 'activity_timeline', ['action_type'], unique=False)
    op.create_index(op.f('ix_activity_timeline_company_id'), 'activity_timeline', ['company_id'], unique=False)
    op.create_index(op.f('ix_activity_timeline_created_at'), 'activity_timeline', ['created_at'], unique=False)

    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_tags_name'), 'tags', ['name'], unique=False)

    op.create_table(
        'company_tags',
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id']),
        sa.PrimaryKeyConstraint('company_id', 'tag_id'),
    )


def downgrade():
    op.drop_table('company_tags')
    op.drop_index(op.f('ix_tags_name'), table_name='tags')
    op.drop_table('tags')
    op.drop_index(op.f('ix_activity_timeline_created_at'), table_name='activity_timeline')
    op.drop_index(op.f('ix_activity_timeline_company_id'), table_name='activity_timeline')
    op.drop_index(op.f('ix_activity_timeline_action_type'), table_name='activity_timeline')
    op.drop_table('activity_timeline')
    op.drop_index(op.f('ix_company_tasks_status'), table_name='company_tasks')
    op.drop_index(op.f('ix_company_tasks_priority'), table_name='company_tasks')
    op.drop_index(op.f('ix_company_tasks_due_date'), table_name='company_tasks')
    op.drop_index(op.f('ix_company_tasks_company_id'), table_name='company_tasks')
    op.drop_table('company_tasks')
    op.drop_index(op.f('ix_company_notes_created_at'), table_name='company_notes')
    op.drop_index(op.f('ix_company_notes_company_id'), table_name='company_notes')
    op.drop_table('company_notes')
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companies_city'))
        batch_op.drop_index(batch_op.f('ix_companies_state'))
        batch_op.drop_column('city')
        batch_op.drop_column('state')
