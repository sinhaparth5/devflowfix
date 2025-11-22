# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import IncidentTable
from app.core.enums import IncidentSource, Severity, Outcome

logger = structlog.get_logger(__name__)

class VectorRepository:
    def __init__(self, session: Session):
        self.session = session

    def store_embedding(
            self,
            incident_id: str,
            embedding: List[float],
    ) -> bool:
        try:
            incident = self.session.query(IncidentTable).filter(
                IncidentTable.incident_id == incident_id
            ).first()

            if not incident:
                raise ValueError(f"Incident not found: {incident_id}")
            
            incident.embedding = embedding
            incident.updated_at = datetime.utcnow()

            self.session.commit()

            logger.info(
                "embeding_stored",
                incident_id=incident_id,
                embedding_dim=len(embedding),
            )

            return True
        except Exception as e:
            self.session.rollback()
            logger.error(
                "embedding_store_failed",
                incident_id=incident_id,
                error=str(e)
            )
            raise

    def search_similar(
            self,
            query_embedding: List[float],
            top_k: int = 5,
            similarity_threshold: float = 0.0,
            source_filter: Optional[IncidentSource] = None,
            severity_filter: Optional[Severity] = None,
            exclude_incident_id: Optional[str] = None,
            only_with_outcome: bool = False,
    ) -> List[Tuple[IncidentSource, float]]:
        try:
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            query = self.session.query(
                IncidentTable,
                (1 - (IncidentTable.embedding.cosine_distance(query_embedding))).label('similarity')
            ).filter(
                IncidentTable.embedding.isnot(None)
            )

            if source_filter:
                query = query.filter(IncidentTable.source == source_filter.value)

            if severity_filter:
                query = query.filter(IncidentTable.severity == severity_filter.value)

            if exclude_incident_id:
                query = query.filter(IncidentTable.outcome.isnot(None))

            query = query.order_by(text('similarity DESC')).limit(top_k)

            results = query.all()

            similar_incidents = [
                (incident, float(similarity))
                for incident, similarity in results
                if similarity >= similarity_threshold
            ]

            logger.info(
                "vector_search_complete",
                num_results=len(similar_incidents),
                top_k=top_k,
                threshold=similarity_threshold,
            )

            return similar_incidents
        except Exception as e:
            logger.error(
                "vector_search_failed",
                error=str(e),
                top_k=top_k,
            )
            raise

    def search_by_incident(
            self,
            incident_id: str,
            top_k: int = 5,
            similarity_threshold: float = 0.7,
            source_filter: Optional[IncidentSource] = None,
    ) -> List[Tuple[IncidentTable, float]]:
        incident = self.session.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id
        ).first()

        if not incident:
            raise ValueError(f"Incident not found: {incident_id}")
        
        if not incident.embedding:
            raise ValueError(f"Incident has no embedding {incident_id}")
        
        return self.search_similar(
            query_embedding=incident.embedding,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            source_filter=source_filter,
            exclude_incident_id=incident_id,
        )
    
    def search_similar_resolved(
            self,
            query_embedding: List[float],
            top_k: int = 5,
            min_confidence: float = 0.7,
            min_similarity: float = 0.6,
    ) -> List[Tuple[IncidentTable, float]]:
        try:
            query = self.session.query(
                IncidentTable,
                (1 - (IncidentTable.embedding.cosine_distance(query_embedding))).label('similarity')
            ).filter(
                IncidentTable.embedding.isnot(None),
                IncidentTable.outcome == Outcome.SUCCESS.value,
            )

            if min_confidence > 0:
                query = query.filter(
                    or_(
                        IncidentTable.confidence >= min_confidence,
                        IncidentTable.confidence.is_(None)
                    )
                )
            
            query = query.order_by(text('similarity DESC')).limit(top_k)

            results = query.all()

            similar_incidents = [
                (incident, float(similarity))
                for incident, similarity in results
                if similarity >= min_similarity
            ]

            logger.info(
                "search_similar_resolved",
                num_results=len(similar_incidents),
                min_confidence=min_confidence,
            )

            return similar_incidents
        except Exception as e:
            logger.error("search_similar_resolved_failed", error=str(e))
            raise
    
    
