"""Update embedding dimension to 4096

Revision ID: f0f73a801d78
Revises: 4a40d469c89a
Create Date: 2025-11-27 22:44:58.769304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'f0f73a801d78'
down_revision: Union[str, Sequence[str], None] = '4a40d469c89a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Drop the IVFFlat index (it doesn't support > 2000 dimensions)
    op.execute("DROP INDEX IF EXISTS idx_incidents_embeddings_ivfflat")
    
    # Step 2: Alter the column dimension using raw SQL
    op.execute("ALTER TABLE incidents ALTER COLUMN embedding TYPE vector(4096)")
    
    # Note: pgvector 0.8.1 has a 2000-dimension limit for indexes (both IVFFlat and HNSW)
    # pgvector 0.9.0+ supports higher dimensions, but Railway uses 0.8.1
    # For now, we'll use exact search (no index) which is slower but functional
    # To add index later when pgvector is upgraded:
    # CREATE INDEX idx_incidents_embeddings_hnsw ON incidents USING hnsw (embedding vector_cosine_ops)


def downgrade() -> None:
    """Downgrade schema."""
    # No index to drop since we're not creating one in upgrade
    
    # Alter column back to 768
    op.execute("ALTER TABLE incidents ALTER COLUMN embedding TYPE vector(768)")
    
    # Recreate IVFFlat index for 768 dimensions
    op.execute("""
        CREATE INDEX idx_incidents_embeddings_ivfflat 
        ON incidents 
        USING ivfflat (embedding vector_cosine_ops)
    """)
