"""add vector index on embeddings

Revision ID: b1dd7fdd5f08
Revises: 65589c7f67a3
Create Date: 2025-11-16 10:16:50.310506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1dd7fdd5f08'
down_revision: Union[str, Sequence[str], None] = '65589c7f67a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: Vector indices (IVFFlat, HNSW) have a 2000 dimension limit in PostgreSQL pgvector
    # Embeddings are 4096 dimensions, so we cannot create a vector index
    # PostgreSQL will still support vector searches using sequential scans
    # If performance becomes an issue, consider reducing embedding dimensions to < 2000
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # No index was created, so nothing to downgrade
    pass
    # ### end Alembic commands ###
