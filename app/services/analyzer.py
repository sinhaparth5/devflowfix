# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Analyzer Service - Core AI-powered incident analysis with RAG.

This service:
1. Takes an incident as input
2. Generates embeddings from error logs using NVIDIA NeMo
3. Searches for similar incidents using vector similarity (RAG)
4. Builds a prompt with context from similar incidents
5. Calls LLM for analysis
6. Returns structured AnalysisResult
"""

import time
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.models.incident import Incident
from app.core.models.analysis import AnalysisResult
from app.core.enums import (
    FailureType,
    Fixability,
    ConfidenceLevel,
)
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AnalyzerService:
    """
    Service for analyzing incidents using AI with RAG (Retrieval-Augmented Generation).
    
    The analyzer combines:
    - Vector similarity search to find similar past incidents
    - LLM-powered analysis for root cause identification
    - Confidence scoring based on multiple signals
    """
    
    def __init__(
        self,
        settings: Settings,
        embedder_service: Optional[Any] = None,
        retriever_service: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        """
        Initialize the analyzer service.
        
        Args:
            settings: Application settings
            embedder_service: Service for generating embeddings
            retriever_service: Service for retrieving similar incidents
            llm_client: Client for calling LLM
        """
        self.settings = settings
        self.embedder = embedder_service
        self.retriever = retriever_service
        self.llm = llm_client
        
        self.rag_top_k = settings.rag_top_k
        self.rag_similarity_threshold = settings.rag_similarity_threshold
        self.llm_model = settings.nvidia_llm_model
        self.llm_temperature = 0.2  
        self.llm_max_tokens = 2000
        
        logger.info(
            "AnalyzerService initialized",
            extra={
                "rag_top_k": self.rag_top_k,
                "similarity_threshold": self.rag_similarity_threshold,
                "llm_model": self.llm_model,
            }
        )
    
    async def analyze(
        self,
        incident: Incident,
        force_reanalysis: bool = False,
    ) -> AnalysisResult:
        """
        Analyze an incident using AI with RAG.
        
        This is the main entry point for incident analysis. It orchestrates:
        1. Embedding generation from error logs
        2. Similar incident retrieval (RAG)
        3. Prompt construction with context
        4. LLM analysis
        5. Confidence calculation
        
        Args:
            incident: The incident to analyze
            force_reanalysis: If True, re-analyze even if already analyzed
            
        Returns:
            AnalysisResult with classification, confidence, and supporting evidence
        """
        start_time = time.time()
        
        logger.info(
            f"Starting analysis for incident {incident.incident_id}",
            extra={
                "incident_id": incident.incident_id,
                "source": incident.source.value,
                "severity": incident.severity.value,
                "force_reanalysis": force_reanalysis,
            }
        )
        
        if not force_reanalysis and incident.root_cause is not None:
            logger.info(
                f"Incident {incident.incident_id} already analyzed, skipping",
                extra={"incident_id": incident.incident_id}
            )
            return self._create_result_from_incident(incident)
        
        try:
            embedding = await self._generate_embedding(incident)
            
            similar_incidents = await self._retrieve_similar_incidents(
                embedding=embedding,
                incident=incident,
            )
            
            prompt = self._build_analysis_prompt(
                incident=incident,
                similar_incidents=similar_incidents,
            )
            
            llm_response = await self._call_llm(prompt)
            
            analysis = self._parse_llm_response(llm_response)
            
            final_confidence = self._calculate_confidence(
                llm_confidence=analysis.get("confidence", 0.5),
                similar_incidents=similar_incidents,
                incident=incident,
            )
            
            result = AnalysisResult(
                category=self._parse_failure_type(analysis.get("category", "unknown")),
                root_cause=analysis.get("root_cause", "Unable to determine root cause"),
                fixability=self._parse_fixability(analysis.get("fixability", "unknown")),
                confidence=final_confidence,
                similar_incidents=[self._format_similar_incident(si) for si in similar_incidents],
                slack_threads=[],  # TODO: Add Slack RAG
                documentation_links=analysis.get("documentation_links", []),
                reasoning=analysis.get("reasoning"),
                llm_model=self.llm_model,
                llm_confidence=analysis.get("confidence", 0.5),
                suggested_actions=analysis.get("suggested_actions", []),
                warnings=analysis.get("warnings", []),
                estimated_fix_duration_seconds=analysis.get("estimated_duration_seconds"),
                analyzed_at=datetime.utcnow(),
                analysis_duration_ms=int((time.time() - start_time) * 1000),
            )
            
            if result.confidence < 0.7:
                result.add_warning(
                    "Low confidence - consider manual review before auto-remediation"
                )
            
            if len(similar_incidents) == 0:
                result.add_warning(
                    "No similar incidents found - this may be a novel failure"
                )
            
            logger.info(
                f"Analysis complete for incident {incident.incident_id}",
                extra={
                    "incident_id": incident.incident_id,
                    "category": result.category.value,
                    "fixability": result.fixability.value,
                    "confidence": result.confidence,
                    "duration_ms": result.analysis_duration_ms,
                    "similar_count": len(similar_incidents),
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"Analysis failed for incident {incident.incident_id}: {e}",
                extra={
                    "incident_id": incident.incident_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            
            return self._create_fallback_result(incident, error=str(e))
    
    async def _generate_embedding(self, incident: Incident) -> List[float]:
        """
        Generate vector embedding from incident error log.
        
        Args:
            incident: Incident to generate embedding for
            
        Returns:
            Embedding vector as list of floats
        """
        if not self.embedder:
            logger.warning("No embedder service available, using zero vector")
            return [0.0] * self.settings.embedding_dimension
        
        try:
            text = self._prepare_embedding_text(incident)
            
            logger.debug(
                f"Generating embedding for incident {incident.incident_id}",
                extra={
                    "incident_id": incident.incident_id,
                    "text_length": len(text),
                }
            )
            
            embedding = await self.embedder.generate_embedding(text)
            
            logger.debug(
                f"Generated embedding with dimension {len(embedding)}",
                extra={
                    "incident_id": incident.incident_id,
                    "dimension": len(embedding),
                }
            )
            
            return embedding
            
        except Exception as e:
            logger.error(
                f"Failed to generate embedding: {e}",
                extra={"incident_id": incident.incident_id},
                exc_info=True,
            )
            return [0.0] * self.settings.embedding_dimension
    
    async def _retrieve_similar_incidents(
        self,
        embedding: List[float],
        incident: Incident,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar incidents using vector similarity search.
        
        Args:
            embedding: Query embedding vector
            incident: Current incident (for filtering)
            
        Returns:
            List of similar incidents with metadata
        """
        if not self.retriever:
            logger.warning("No retriever service available")
            return []
        
        try:
            similar = await self.retriever.search_similar_incidents(
                embedding=embedding,
                top_k=self.rag_top_k,
                similarity_threshold=self.rag_similarity_threshold,
                exclude_incident_id=incident.incident_id,
                filters={
                    "source": incident.source.value, 
                },
            )
            
            logger.info(
                f"Retrieved {len(similar)} similar incidents",
                extra={
                    "incident_id": incident.incident_id,
                    "count": len(similar),
                    "top_similarity": similar[0].get("similarity") if similar else None,
                }
            )
            
            return similar
            
        except Exception as e:
            logger.error(
                f"Failed to retrieve similar incidents: {e}",
                extra={"incident_id": incident.incident_id},
                exc_info=True,
            )
            return []
    
    def _build_analysis_prompt(
        self,
        incident: Incident,
        similar_incidents: List[Dict[str, Any]],
    ) -> str:
        """
        Build the LLM prompt with context from RAG.
        
        Args:
            incident: Current incident to analyze
            similar_incidents: Similar incidents from vector search
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert DevOps AI analyzing a CI/CD failure incident.

## Current Incident

**Source:** {incident.source.value}
**Severity:** {incident.severity.value}
**Timestamp:** {incident.timestamp.isoformat()}

**Error Log:**
```
{incident.error_log[:2000]}  
```

**Context:**
{self._format_context(incident.context)}

"""
        
        if similar_incidents:
            prompt += "\n## Similar Past Incidents (for context)\n\n"
            
            for i, similar in enumerate(similar_incidents[:3], 1):  
                prompt += f"### Similar Incident #{i} (similarity: {similar.get('similarity', 0):.2f})\n\n"
                prompt += f"**Root Cause:** {similar.get('root_cause', 'Unknown')}\n"
                prompt += f"**Fixability:** {similar.get('fixability', 'unknown')}\n"
                prompt += f"**Outcome:** {similar.get('outcome', 'unknown')}\n"
                
                if similar.get('resolution_time_seconds'):
                    prompt += f"**Resolution Time:** {similar['resolution_time_seconds']}s\n"
                
                prompt += "\n"
        else:
            prompt += "\n## Note\nNo similar incidents found in history - this may be a novel failure.\n\n"
        
        prompt += """
## Your Task

Analyze this incident and provide:

1. **Category**: Classify the failure type (e.g., imagepullbackoff, buildfailure, testfailure, etc.)
2. **Root Cause**: Explain the root cause in 1-2 sentences
3. **Fixability**: Can this be automatically fixed? (auto/manual/unknown)
4. **Confidence**: Your confidence in this analysis (0.0-1.0)
5. **Suggested Actions**: List 2-3 specific actions to resolve this
6. **Warnings**: Any warnings or caveats about the suggested fix
7. **Estimated Duration**: Estimated time to fix in seconds

## Output Format

Respond ONLY with a valid JSON object:

```json
{
  "category": "failure_type_here",
  "root_cause": "Brief explanation of root cause",
  "fixability": "auto|manual|unknown",
  "confidence": 0.85,
  "reasoning": "Why you reached this conclusion",
  "suggested_actions": [
    "Action 1",
    "Action 2"
  ],
  "warnings": [
    "Warning if any"
  ],
  "estimated_duration_seconds": 300,
  "documentation_links": []
}
```

Be concise, accurate, and consider the similar incidents when available.
"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM for analysis.
        
        Args:
            prompt: The analysis prompt
            
        Returns:
            LLM response text
        """
        if not self.llm:
            logger.warning("No LLM client available")
            return self._get_fallback_llm_response()
        
        try:
            response = await self.llm.generate(
                prompt=prompt,
                model=self.llm_model,
                temperature=self.llm_temperature,
                max_tokens=self.llm_max_tokens,
            )
            
            return response
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return self._get_fallback_llm_response()
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM response JSON.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            Parsed response dictionary
        """
        import json
        import re
        
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            
            parsed = json.loads(response)
            return parsed
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}", exc_info=True)
            
            return {
                "category": "unknown",
                "root_cause": "Unable to parse LLM response",
                "fixability": "unknown",
                "confidence": 0.3,
                "reasoning": f"Parse error: {str(e)}",
                "suggested_actions": ["Manual investigation required"],
                "warnings": ["Automated analysis failed"],
            }
    
    def _calculate_confidence(
        self,
        llm_confidence: float,
        similar_incidents: List[Dict[str, Any]],
        incident: Incident,
    ) -> float:
        """
        Calculate final confidence score from multiple signals.
        
        Combines:
        - LLM's own confidence
        - Vector similarity scores
        - Historical success rate of similar incidents
        
        Args:
            llm_confidence: Confidence from LLM
            similar_incidents: Similar incidents from RAG
            incident: Current incident
            
        Returns:
            Final confidence score (0.0-1.0)
        """
        confidence = llm_confidence * 0.5
        
        if similar_incidents:
            top_similarities = [
                si.get("similarity", 0.0)
                for si in similar_incidents[:3]
            ]
            avg_similarity = sum(top_similarities) / len(top_similarities)
            confidence += avg_similarity * 0.3
            
            successful = sum(
                1 for si in similar_incidents[:5]
                if si.get("outcome") == "success"
            )
            success_rate = successful / min(len(similar_incidents), 5)
            confidence += success_rate * 0.2
        else:
            confidence *= 0.7
        
        return max(0.0, min(1.0, confidence))
    
    def _prepare_embedding_text(self, incident: Incident) -> str:
        """
        Prepare text for embedding generation.
        
        Combines error log with relevant context.
        
        Args:
            incident: Incident to prepare text for
            
        Returns:
            Text for embedding
        """
        parts = []
        
        parts.append(f"Source: {incident.source.value}")
        parts.append(f"Severity: {incident.severity.value}")
        
        if incident.error_message:
            parts.append(f"Error: {incident.error_message}")
        
        parts.append(incident.error_log[:1500]) 
        
        if incident.context:
            if "repository" in incident.context:
                parts.append(f"Repository: {incident.context['repository']}")
            if "service" in incident.context:
                parts.append(f"Service: {incident.context['service']}")
        
        return "\n".join(parts)
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format incident context for prompt."""
        if not context:
            return "No additional context available"
        
        lines = []
        for key, value in context.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"- {key}: {value}")
        
        return "\n".join(lines) if lines else "No additional context available"
    
    def _format_similar_incident(self, similar: Dict[str, Any]) -> dict:
        """Format similar incident for result."""
        return {
            "incident_id": similar.get("incident_id"),
            "similarity": similar.get("similarity"),
            "root_cause": similar.get("root_cause"),
            "outcome": similar.get("outcome"),
            "resolution_time_seconds": similar.get("resolution_time_seconds"),
            "context": similar.get("context", {}),
        }
    
    def _parse_failure_type(self, category: str) -> FailureType:
        """Parse failure type from string."""
        try:
            return FailureType(category.lower())
        except (ValueError, AttributeError):
            return FailureType.UNKNOWN
    
    def _parse_fixability(self, fixability: str) -> Fixability:
        """Parse fixability from string."""
        try:
            return Fixability(fixability.lower())
        except (ValueError, AttributeError):
            return Fixability.UNKNOWN
    
    def _create_result_from_incident(self, incident: Incident) -> AnalysisResult:
        """Create AnalysisResult from already-analyzed incident."""
        return AnalysisResult(
            category=incident.failure_type or FailureType.UNKNOWN,
            root_cause=incident.root_cause or "Previously analyzed",
            fixability=incident.fixability or Fixability.UNKNOWN,
            confidence=incident.confidence or 0.5,
            similar_incidents=[
                self._format_similar_incident(si)
                for si in incident.similar_incidents
            ] if incident.similar_incidents else [],
            analyzed_at=incident.updated_at or datetime.utcnow(),
        )
    
    def _create_fallback_result(
        self,
        incident: Incident,
        error: str,
    ) -> AnalysisResult:
        """Create fallback result when analysis fails."""
        return AnalysisResult(
            category=FailureType.UNKNOWN,
            root_cause=f"Analysis failed: {error}",
            fixability=Fixability.MANUAL,
            confidence=0.0,
            warnings=[
                "Automated analysis failed",
                "Manual investigation required",
                f"Error: {error}",
            ],
            analyzed_at=datetime.utcnow(),
        )
    
    def _get_fallback_llm_response(self) -> str:
        """Get fallback LLM response when LLM is unavailable."""
        return """{
            "category": "unknown",
            "root_cause": "LLM service unavailable",
            "fixability": "unknown",
            "confidence": 0.0,
            "reasoning": "LLM client not available",
            "suggested_actions": ["Manual investigation required"],
            "warnings": ["LLM analysis unavailable"]
        }"""
