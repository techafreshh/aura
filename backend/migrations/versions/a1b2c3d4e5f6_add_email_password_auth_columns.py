"""add email/password auth columns to users

Revision ID: a1b2c3d4e5f6
Revises: 34be358114eb
Create Date: 2026-09-13 15:06:39.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '34be358114eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add password/email-verification columns.

    ``server_default=sa.false()`` is required so ``email_verified`` can be
    added as NOT NULL on a table with existing rows. Kept in sync with
    ``db.database._USER_COLUMNS_ADDED`` and ``db.models.User``.
    """
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column(
        'users',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('users', sa.Column('verification_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('verification_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('reset_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop password/email-verification columns."""
    op.drop_column('users', 'reset_token_expires_at')
    op.drop_column('users', 'reset_token_hash')
    op.drop_column('users', 'verification_token_expires_at')
    op.drop_column('users', 'verification_token_hash')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'password_hash')
