# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""initial schema

Revision ID: 001
Revises: 
Create Date: 2025-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables for the DevFlowFix application."""
    
    # Incidents table
    op.create_table(
        'incidents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='open'),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for incidents
    op.create_index('idx_incidents_status', 'incidents', ['status'])
    op.create_index('idx_incidents_severity', 'incidents', ['severity'])
    op.create_index('idx_incidents_source', 'incidents', ['source', 'source_id'])
    op.create_index('idx_incidents_created_at', 'incidents', ['created_at'])
    
    # Analysis table
    op.create_table(
        'analyses',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('incident_id', sa.String(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('analysis_type', sa.String(100), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('findings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    op.create_index('idx_analyses_incident_id', 'analyses', ['incident_id'])
    op.create_index('idx_analyses_type', 'analyses', ['analysis_type'])
    
    # Remediations table
    op.create_table(
        'remediations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('incident_id', sa.String(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('analysis_id', sa.String(), sa.ForeignKey('analyses.id', ondelete='SET NULL'), nullable=True),
        sa.Column('remediation_type', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    op.create_index('idx_remediations_incident_id', 'remediations', ['incident_id'])
    op.create_index('idx_remediations_status', 'remediations', ['status'])
    op.create_index('idx_remediations_type', 'remediations', ['remediation_type'])
    
    # Feedback table for learning from past incidents
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('incident_id', sa.String(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('remediation_id', sa.String(), sa.ForeignKey('remediations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('was_helpful', sa.Boolean(), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    op.create_index('idx_feedback_incident_id', 'feedback', ['incident_id'])
    op.create_index('idx_feedback_rating', 'feedback', ['rating'])
    

def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('feedback')
    op.drop_table('remediations')
    op.drop_table('analyses')
    op.drop_table('incidents')
