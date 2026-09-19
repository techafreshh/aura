"""dual roles + per-role profile tables

Revision ID: c3d4e5f6a7b8
Revises: b8e2802f0d1b
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b8e2802f0d1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the recruiter capability flag and the two profile tables."""
    # NOT NULL with a server_default so existing rows backfill cleanly on both
    # SQLite and Postgres; the flag is then granted to anyone who had already
    # chosen the recruiter role, so no recruiter loses access after upgrade.
    op.add_column(
        'users',
        sa.Column('is_recruiter', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("UPDATE users SET is_recruiter = 1 WHERE role = 'recruiter'")

    op.create_table('candidate_profiles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('headline', sa.String(length=200), nullable=False),
    sa.Column('location', sa.String(length=120), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('skills_json', sa.Text(), nullable=False),
    sa.Column('experience_json', sa.Text(), nullable=False),
    sa.Column('education_json', sa.Text(), nullable=False),
    sa.Column('linkedin_url', sa.String(length=512), nullable=True),
    sa.Column('github_url', sa.String(length=512), nullable=True),
    sa.Column('portfolio_url', sa.String(length=512), nullable=True),
    sa.Column('resume_stored', sa.Boolean(), nullable=False),
    sa.Column('resume_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', name='uq_candidate_profiles_user')
    )
    op.create_index(op.f('ix_candidate_profiles_user_id'), 'candidate_profiles', ['user_id'], unique=True)

    op.create_table('recruiter_profiles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('job_title', sa.String(length=120), nullable=False),
    sa.Column('company_website', sa.String(length=512), nullable=True),
    sa.Column('company_location', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', name='uq_recruiter_profiles_user')
    )
    op.create_index(op.f('ix_recruiter_profiles_user_id'), 'recruiter_profiles', ['user_id'], unique=True)


def downgrade() -> None:
    """Remove the profile tables and the capability flag (role is untouched)."""
    op.drop_index(op.f('ix_recruiter_profiles_user_id'), table_name='recruiter_profiles')
    op.drop_table('recruiter_profiles')
    op.drop_index(op.f('ix_candidate_profiles_user_id'), table_name='candidate_profiles')
    op.drop_table('candidate_profiles')
    op.drop_column('users', 'is_recruiter')
