# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import structlog

from app.core.models.incident import Incident
from app.core.enums import IncidentSource, Outcome
from app.adapters.ai.nvidia import EmbeddingAdapter
from app.adapters.database.postgres.repositories.vector import VectorRepository
from app.adapters.database.postgres.models import IncidentTable

logger = structlog.get_logger(__name__)

class RetrieverService:
    def __init__(
        self,
        embedding_adapter: EmbeddingAdapter,
        vector_repository: Optional[VectorRepository] = None,
        default_top_k: int = 5,
        default_similarity_threshold: float = 0.7,
        cache_ttl_seconds: int = 300,
    ):
        self.embedding_adapter = embedding_adapter
        self.vector_repo = vector_repository
        self.default_top_k = default_top_k
        self.default_similarity_threshold = default_similarity_threshold
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, Tuple[List[Dict], datetime]] = {}

    async def retrieve_similar_incidents(
            self,
            incident: Incident,
            top_k: Optional[int] = None,
            similarity_threshold: Optional[float] = None,
            source_filter: Optional[IncidentSource] = None,
            only_resolved: bool = False,
            min_confidence: float = 0.0,
            max_age_days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k or self.default_top_k
        similarity_threshold = similarity_threshold or self.default_similarity_threshold

        cache_key = self._build_cache_key(incident.incident_id, top_k, source_filter, only_resolved)
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.debug("cache_hit", incident_id=incident.incident_id)
            return cached
        
        if not self.vector_repo:
            logger.warning("vector_repo_not_configured")
            return []
        
        try:
            if only_resolved:
                embedding = await self._get_or_create_embedding(incident)
                if not embedding:
                    return []
                
                similar = self.vector_repo.search_similar_resolved(
                    query_embedding=embedding,
                    top_k=top_k,
                    min_confidence=min_confidence,   
                )
            else:
                similar = self.vector_repo.search_by_incident(
                    incident_id=incident.incident_id,
                    top_k=top_k,
                    min_confidence=min_confidence,
                )

            results = self._transform_results(similar, max_age_days)

            self._set_cache(cache_key, results)

            logger.info(
                "similar_incidents_retrieved",
                incident_id=incident.incident_id,
                count=len(results),
                top_k=top_k,
            )

            return results
        
        except Exception as e:
            logger.error(
                "retrieval_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )

            return []
    
    async def retrieve_by_query(
            self,
            query: str,
            top_k: Optional[int] = None,
            similarity_threshold: Optional[float] = None,
            source_filter: Optional[IncidentSource] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k or self.default_top_k
        similarity_threshold = similarity_threshold or self.default_similarity_threshold

        if not self.vector_repo:
            logger.warning("vector_repo_not_configured")
            return []
        
        try:
            embedding = await self.embedding_adapter.embed(query)

            similar = self.vector_repo.search_similar(
                query_embedding=embedding,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                source_filter=source_filter,
            )

            results = self._transform_results(similar)

            logger.info(
                "query_retrieval_complete",
                query_length=len(query),
                count=len(results),
            )

            return results
        
        except Exception as e:
            logger.error("query_retrieval_failed", error=str(e))
            return []
        
    async def retrieve_for_rag_context(
            self,
            incident: Incident,
            max_context_items: int = 3,
            min_similarity: float = 0.75,
    ) -> Dict[str, Any]:
        similar = await self.retrieve_similar_incidents(
            incident=incident,
            top_k=max_context_items * 2,
            similarity_threshold=min_similarity,
            only_resolved=True,
            min_confidence=0.7,
        )
        context_items = []
        for item in similar[:max_context_items]:
            context_items.append({
                "incident_id": item.get("incidents_id"),
                "similarity": item.get("similarity"),
                "root_cause": item.get("root_cause"),
                "remediation_actions": item.get("remediation_actions", []),
                "outcome": item.get("outcome"),
                "resolution_time": item.get("resolution_time_seconds"),
            })

            success_count = sum(1 for item in context_items if item.get("outcome") == "success")
            avg_similarity = sum(item.get("similarity", 0) for item in context_items) / len(context_items)

            return {
                "similar_incidents": context_items,
                "total_found": len(similar),
                "success_rate": success_count / len(context_items) if context_items else 0,
                "average_similarity": avg_similarity,
                "has_high_confidence_match": any(item.get("similarity", 0) > 0.9 for item in context_items),
            }
        
    async def find_related_pattern(
            self,
            incident: Incident,
            time_window_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        
        similar = await self.retrieve_similar_incidents(
            incident=incident,
            top_k=20,
            similarity_threshold=0.8,
        )

        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        recent_similar = []
        for item in similar:
            created_at = item.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                if created_at >= cutoff_time:
                    recent_similar.append(item)

        return recent_similar

    async def embed_and_store(self, incident: Incident) -> bool:
        if not self.vector_repo:
            return False
        
        try:
            embedding = await self.embedding_adapter.embed_incident(
                error_log=incident.error_log,
                context=incident.context,
            )
            
            self.vector_repo.store_embedding(incident.incident_id, embedding)
            
            logger.info(
                "embedding_stored",
                incident_id=incident.incident_id,
                dimension=len(embedding),
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "embed_and_store_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )
            return False
    
    async def batch_embed_and_store(
        self,
        incidents: List[Incident],
        batch_size: int = 10,
    ) -> Dict[str, Any]:
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        for i in range(0, len(incidents), batch_size):
            batch = incidents[i:i + batch_size]
           
            for incident in batch:
                try:
                    success = await self.embed_and_store(incident)
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_ids.append(incident.incident_id)
                except Exception as e:
                    failed_count += 1
                    failed_ids.append(incident.incident_id)
                    logger.error("batch_embed_failed", incident_id=incident.incident_id, error=str(e))
        
        logger.info(
            "batch_embedding_complete",
            total=len(incidents),
            success=success_count,
            failed=failed_count,
        )
        
        return {
            "total": len(incidents),
            "success": success_count,
            "failed": failed_count,
            "failed_ids": failed_ids,
        }

    async def get_embedding_coverage(self) -> Dict[str, Any]:
        if not self.vector_repo:
            return {"error": "vector_repo_not_configured"}
        
        return self.vector_repo.get_embedding_stats()
    
    async def _get_or_create_embedding(self, incident: Incident) -> Optional[List[float]]:
        try:
            return await self.embedding_adapter.embed_incident(
                error_log=incident.error_log,
                context=incident.context,
            )
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return None
    
    def _transform_results(
        self,
        results: List[Tuple[IncidentTable, float]],
        max_age_days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        
        transformed = []
        cutoff_date = None
        
        if max_age_days:
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
        
        for incident_table, similarity in results:
            if cutoff_date and incident_table.created_at < cutoff_date:
                continue
            
            transformed.append({
                "incident_id": incident_table.incident_id,
                "similarity": round(similarity, 4),
                "source": incident_table.source,
                "severity": incident_table.severity,
                "failure_type": incident_table.failure_type,
                "root_cause": incident_table.root_cause,
                "outcome": incident_table.outcome,
                "confidence": incident_table.confidence,
                "remediation_plan": incident_table.remediation_plan,
                "remediation_actions": self._extract_actions(incident_table.remediation_plan),
                "resolution_time_seconds": incident_table.resolution_time_seconds,
                "created_at": incident_table.created_at.isoformat() if incident_table.created_at else None,
                "resolved_at": incident_table.resolved_at.isoformat() if incident_table.resolved_at else None,
            })
        
        return transformed
    
    def _extract_actions(self, remediation_plan: Optional[Dict]) -> List[str]:
        if not remediation_plan:
            return []
        
        actions = remediation_plan.get("actions_performed", [])
        if not actions:
            action_type = remediation_plan.get("action_type")
            if action_type:
                actions = [action_type]
        
        return actions
    
    def _build_cache_key(
        self,
        incident_id: str,
        top_k: int,
        source_filter: Optional[IncidentSource],
        only_resolved: bool,
    ) -> str:
        parts = [incident_id, str(top_k)]
        if source_filter:
            parts.append(source_filter.value)
        if only_resolved:
            parts.append("resolved")
        return ":".join(parts)
    
    def _get_from_cache(self, key: str) -> Optional[List[Dict]]:
        if key not in self._cache:
            return None
        
        results, timestamp = self._cache[key]
        
        if datetime.utcnow() - timestamp > timedelta(seconds=self.cache_ttl_seconds):
            del self._cache[key]
            return None
        
        return results
    
    def _set_cache(self, key: str, results: List[Dict]):
        self._cache[key] = (results, datetime.utcnow())
        
        if len(self._cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        now = datetime.utcnow()
        expired_keys = [
            k for k, (_, ts) in self._cache.items()
            if now - ts > timedelta(seconds=self.cache_ttl_seconds)
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def clear_cache(self):
        self._cache.clear()
        logger.info("retriever_cache_cleared") 