"""Add search string templates table

Revision ID: a8b9c0d1e2f3
Revises: f7b8c9d0e1f2
Create Date: 2025-07-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'f7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'search_string_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('industry', sa.String(length=200), nullable=False),
        sa.Column('search_strings', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_search_string_templates_name'), 'search_string_templates', ['name'], unique=False)
    op.create_index(op.f('ix_search_string_templates_industry'), 'search_string_templates', ['industry'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_search_string_templates_industry'), table_name='search_string_templates')
    op.drop_index(op.f('ix_search_string_templates_name'), table_name='search_string_templates')
    op.drop_table('search_string_templates')
