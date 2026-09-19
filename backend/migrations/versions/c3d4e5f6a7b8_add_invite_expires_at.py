"""add invite expires_at

Revision ID: c3d4e5f6a7b8
Revises: b8e2802f0d1b
Create Date: 2026-09-19 09:00:00.000000

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
    """Add the invite link expiry column.

    Nullable with no default: pre-existing invites read as ``expires_at = NULL``
    (never expire), and new invites get their value computed in
    ``db.crud.create_invite`` so the 24-hour default lives in one place.
    """
    op.add_column(
        'interview_invites',
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('interview_invites', 'expires_at')
