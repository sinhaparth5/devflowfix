# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""enable pgvector extension and create vector tables

Revision ID: 002
Revises: 001
Create Date: 2025-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector extension and create vector-based tables."""
    
    # Enable pgvector extension
    op.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    
    # Incident embeddings table for semantic search
    op.create_table(
        'incident_embeddings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('incident_id', sa.String(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('embedding', sa.Text(), nullable=False),  # Will be VECTOR type
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Alter the embedding column to use vector type (1536 dimensions for OpenAI embeddings)
    op.execute(text('ALTER TABLE incident_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector'))
    
    # Create an index for fast similarity search using cosine distance
    op.execute(text('CREATE INDEX idx_incident_embeddings_vector ON incident_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)'))
    
    op.create_index('idx_incident_embeddings_incident_id', 'incident_embeddings', ['incident_id'])
    
    # Knowledge base table for storing past solutions and patterns
    op.create_table(
        'knowledge_base',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('tags', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('embedding', sa.Text(), nullable=False),  # Will be VECTOR type
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('source_incident_ids', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('usefulness_score', sa.Float(), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Alter the embedding column to use vector type
    op.execute(text('ALTER TABLE knowledge_base ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector'))
    
    # Create an index for fast similarity search
    op.execute(text('CREATE INDEX idx_knowledge_base_vector ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)'))
    
    op.create_index('idx_knowledge_base_category', 'knowledge_base', ['category'])
    op.create_index('idx_knowledge_base_tags', 'knowledge_base', ['tags'], postgresql_using='gin')
    

def downgrade() -> None:
    """Remove vector tables and extension."""
    op.drop_table('knowledge_base')
    op.drop_table('incident_embeddings')
    op.execute(text('DROP EXTENSION IF EXISTS vector'))
