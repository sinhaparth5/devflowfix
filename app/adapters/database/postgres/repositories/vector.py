# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
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
            incident.updated_at = datetime.now(timezone.utc)

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
                query = query.filter(IncidentTable.incident_id != exclude_incident_id)

            if only_with_outcome:
                query = query.filter(IncidentTable.outcome.isnot(None))

            query = query.order_by(text('similarity DESC')).limit(top_k)

            results = query.all()

            similar_incidents = [
                (incident, float(similarity))
                for incident, similarity in results
                if float(similarity) >= similarity_threshold
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
            min_confidence: float = 0.0,
    ) -> List[Tuple[IncidentTable, float]]:
        incident = self.session.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id
        ).first()

        if not incident:
            raise ValueError(f"Incident not found: {incident_id}")
        
        # Check if embedding is None or empty (handle array-like embeddings)
        if incident.embedding is None or (isinstance(incident.embedding, (list, tuple)) and len(incident.embedding) == 0):
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
                if float(similarity) >= min_similarity
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
    

    def search_recent_similar(
            self,
            query_embedding: List[float],
            hours: int = 24,
            top_k: int = 10,
            similarity_threshold: float = 0.7,
    ) -> List[Tuple[IncidentTable, float]]:
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            query = self.session.query(
                IncidentTable,
                (1 - (IncidentTable.embedding.cosine_distance(query_embedding))).label('similarity')   
            ).filter(
                IncidentTable.embedding.isnot(None),
                IncidentTable.created_at >= cutoff_time,
            ).order_by(
                text('similarity DESC')
            ).limit(top_k)

            results = query.all()

            return [
                (incident, float(similarity))
                for incident, similarity in results
                if float(similarity) >= similarity_threshold
            ]
        
        except Exception as e:
            logger.error("search_recent_similar_failed", error=str(e))
            raise

    def get_incidents_without_embeddings(
            self,
            limit: int = 100,
            source_filter: Optional[IncidentSource] = None,
    ) -> List[IncidentTable]:
        try:
            query = self.session.query(IncidentTable).filter(
                IncidentTable.embedding.is_(None)
            )

            if source_filter:
                query = query.filter(IncidentTable.source == source_filter.value)

                incidents = query.order_by(
                    IncidentTable.created_at.desc()
                ).limit(limit).all()

                logger.info(
                    "incident_without_embeddings",
                    count=len(incidents),
                    limit=limit,
                )

                return incidents
            
        except Exception as e:
            logger.error("get_incidents_without_embeddings_failed", error=str(e))
            raise

    def bulk_store_embeddings(
            self,
            embeddings: Dict[str, List[float]],
    ) -> Dict[str, Any]:
        success_count = 0
        failed_count = 0
        failed_ids = []

        try:
            for incident_id, embedding in embeddings.items():
                incident = self.session.query(IncidentTable).filter(
                    IncidentTable.incident_id == incident_id
                ).first()

                if incident:
                    incident.embedding = embedding
                    incident.updated_at = datetime.now(timezone.utc)
                    success_count += 1
                else:
                    failed_count += 1
                    failed_ids.append(incident_id)
            
            self.session.commit()

            logger.info(
                "bulk_embeddings_stored",
                success=success_count,
                failed=failed_count,
            )

            return {
                "success": success_count,
                "failed": failed_count,
                "failed_ids": failed_ids,
            }
        
        except Exception as e:
            self.session.rollback()
            logger.error("bulk_embeddings_store_failed", error=str(e))
            raise
        
    def count_incidents_with_embeddings(self) -> int:
        try:
            count = self.session.query(
                func.count(IncidentTable.incident_id)
            ).filter(
                IncidentTable.embedding.isnot(None)
            ).scalar()

            return count or 0
        
        except Exception as e:
            logger.error("count_embeddings_failed", error=str(e))
            raise

    def get_embedding_stats(self) -> Dict[str, Any]:
        try:
            total_incidents = self.session.query(
                func.count(IncidentTable.incident_id)
            ).scalar() or 0

            with_embeddings = self.count_incidents_with_embeddings()
            without_embeddings = total_incidents - with_embeddings
            coverage = (with_embeddings / total_incidents * 100) if total_incidents > 0 else 0
            
            by_source = {}
            source_counts = self.session.query(
                IncidentTable.source,
                func.count(IncidentTable.incident_id)
            ).filter(
                IncidentTable.embedding.isnot(None)
            ).group_by(
                IncidentTable.source
            ).all()

            for source, count in source_counts:
                by_source[source] = count

            by_outcome = {}
            outcome_counts = self.session.query(
                IncidentTable.outcome,
                func.count(IncidentTable.incident_id)
            ).filter(
                IncidentTable.embedding.isnot(None)
            ).group_by(
                IncidentTable.outcome
            ).all()

            for outcome, count in outcome_counts:
                by_outcome[outcome or "pending"] = count

            stats = {
                "total_incidents": total_incidents,
                "with_embeddings": with_embeddings,
                "without_embeddings": without_embeddings,
                "coverage_percent": round(coverage, 2),
                "by_source": by_source,
                "by_outcome": by_outcome,
            }

            logger.info("embedding_stats", **stats)

            return stats
        
        except Exception as e:
            logger.error("embedding_stats_failed", error=str(e))
            raise

    def get_average_similarity(
            self,
            incident_id: str,
            top_k: int = 5,
    ) -> Optional[float]:
        try:
            similar = self.search_by_incident(
                incident_id=incident_id,
                top_k=top_k,
                similarity_threshold=0.0,
            )

            if not similar:
                return None
            
            avg_similarity = sum(sim for _, sim in similar) / len(similar)

            logger.debug(
                "average_similarity_calculated",
                incident_id=incident_id,
                avg_similarity=avg_similarity,
                num_similar=len(similar),
            )

            return round(avg_similarity, 4)
        
        except Exception as e:
            logger.error("average_similarity_failed", error=str(e))
            return None
        
    def find_duplicates(
            self,
            incident_id: str,
            similarity_threshold: float = 0.95,
    ) -> List[Tuple[IncidentTable, float]]:
        try:
            return self.search_by_incident(
                incident_id=incident_id,
                top_k=10,
                similarity_threshold=similarity_threshold,
            )
        except Exception as e:
            logger.error("find_duplicates_failed", error=str(e))
            return []
        
    def delete_embedding(self, incident_id: str) -> bool:
        try:
            incident = self.session.query(IncidentTable).filter(
                IncidentTable.incident_id == incident_id
            ).first()

            if not incident:
                return False
            
            incident.embedding = None
            incident.updated_at = datetime.now(timezone.utc)

            self.session.commit()

            logger.info("embedding_deleted", incident_id=incident_id)

            return True
        
        except Exception as e:
            self.session.rollback()
            logger.error("embedding_delete_failed", error=str(e))
            raise

    def delete_all_embeddings(self) -> int:
        try:
            count = self.session.query(IncidentTable).filter(
                IncidentTable.embedding.isnot(None)
            ).update(
                {IncidentTable.embedding: None, IncidentTable.updated_at: datetime.now(timezone.utc)},
                synchronize_session=False
            )

            self.session.commit()

            logger.info("all_embeddings_deleted", count=count)

            return count
        
        except Exception as e:
            self.session.rollback()
            logger.error("delete_all_embeddings_failed", error=str(e))
            raise

    def get_incident_with_embedding(
            self,
            incident_id: str,
    ) -> Optional[Tuple[IncidentTable, List[float]]]:
        try:
            incident = self.session.query(IncidentTable).filter(
                IncidentTable.incident_id == incident_id
            ).first()

            if not incident or not incident.embedding:
                return None
            
            return (incident, list(incident.embedding))
        
        except Exception as e:
            logger.error("get_incident_with_embedding_failed", error=str(e))
            return None
        
    def has_embedding(self, incident_id: str) -> bool:
        try:
            result = self.session.query(
                func.count(IncidentTable.incident_id)
            ).filter(
                IncidentTable.incident_id == incident_id,
                IncidentTable.embedding.isnot(None)
            ).scalar()

            return result > 0
        
        except Exception as e:
            logger.error("has_embedding_check_failed", error=str(e))
            return False
