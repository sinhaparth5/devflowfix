# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
import structlog

from app.domain.strategies.base import BaseStrategy, DecisionResult
from app.domain.strategies.factory import StrategyFactory
from app.domain.rules.base import BaseRule
from app.domain.rules.blacklist import BlacklistRule
from app.domain.rules.blast_radius import BlastRadiusRule
from app.domain.rules.time_window import TimeWindowRule
from app.domain.rules.environment import EnvironmentRule
from app.domain.rules.confidence import ConfidenceRule
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext
from app.core.enums import Environment, StrategyType

logger = structlog.get_logger(__name__)

class DecisionService:
    def __init__(
            self,
            strategy: Optional[BaseStrategy] = None,
            enable_rules: bool = True,
    ):
        self.strategy = strategy or StrategyFactory.create()
        self.enable_rules = enable_rules
        self.rules = self._initialize_rules() if enable_rules else []

        logger.info(
            "decision_service_initializer",
            strategy=self.strategy.name,
            num_rules=len(self.rules),
        )

    def _initialize_rules(self) ->list[BaseRule]:
        return [
            BlacklistRule(),
            BlastRadiusRule(),
            TimeWindowRule(),
            EnvironmentRule(),
            ConfidenceRule(),
        ]
    
    def decide(
            self,
            analysis: AnalysisResult,
            incident: Incident,
            context: ExecutionContext,
            similar_incidents: Optional[list] = None,
    ) -> DecisionResult:
        logger.info(
            "decision_start",
            incident_id=incident.incident_id,
            strategy=self.strategy.name,
            environment=context.environment.value,
        )

        if self.enable_rules:
            rule_result = self._apply_rules(incident, context, analysis)
            if not rule_result["allowed"]:
                logger.info(
                    "decision_blocked_by_rule",
                    incident_id=incident.incident_id,
                    rule=rule_result["blocked_by"],
                    reason=rule_result["reason"],
                )

                return DecisionResult(
                    should_auto_fix=False,
                    confidence=0.0,
                    reason=f"Blocked by rule: {rule_result['reason']}",
                    strategy_name=self.strategy.name,
                    factors={"blocked_by_rule": rule_result["blocked_by"]},
                    escalate=rule_result.get("escalate", False),
                )
        
        decision = self.strategy.decide(
            analysis=analysis,
            incident=incident,
            context=context,
            similar_incidents=similar_incidents,
        )

        if decision.should_auto_fix:
            blast_radius_ok, blast_reason = self.strategy.apply_blast_radius_check(
                incident, context
            )

            if not blast_radius_ok:
                logger.warning(
                    "decision_blocked_by_blast_radius",
                    incident_id=incident.incident_id,
                    reason=blast_reason,
                )

                decision.should_auto_fix = False
                decision.reason = blast_reason
                decision.requires_approval = True
                decision.factors["blast_radius_exceeded"] = True

        if decision.should_auto_fix and context.is_production():
            if not self._verify_production_safety(analysis, incident, context):
                logger.warning(
                    "decision_blocked_by_production_safety",
                    incident_id=incident.incident_id,
                )

                decision.should_auto_fix = False
                decision.reason = "Production safety check failed"
                decision.requires_approval = True
                decision.factors["production_safety_failed"] = True
        
        logger.info(
            "decision_complete",
            incident_id=incident.incident_id,
            should_auto_fix=decision.should_auto_fix,
            confidence=decision.confidence,
            requires_approval=decision.requires_approval,
        )

        return decision
    
    def _apply_rules(
            self,
            incident: Incident,
            context: ExecutionContext,
            analysis: AnalysisResult,
    ) -> dict:
        for rule in self.rules:
            if not rule.evaluate(incident, context, analysis):
                return {
                    "allowed": False,
                    "blocked_by": rule.name,
                    "reason": rule.get_failure_reason(),
                    "escalate": getattr(rule, "escalate_on_failure", False),
                }
        
        return { "allowed": True }
    
    def _verify_production_safety(
            self,
            analysis: AnalysisResult,
            incident: Incident,
            context: ExecutionContext,
    ) -> bool:
        if analysis.confidence < 0.95:
            return False
        
        if not analysis.similar_incidents or len(analysis.similar_incidents) < 2:
            return False
        
        successful_similar = [
            inc for inc in analysis.similar_incidents
            if inc.get("outcome") == "success"
        ]

        if len(successful_similar) < 2:
            return False
        
        if incident.severity.value == "critical":
            top_similarity = analysis.similar_incidents[0].get("similarity", 0)
            if top_similarity < 0.95:
                return False
        
        return True
    
    def set_strategy(self, strategy: BaseStrategy):
        self.strategy = strategy
        logger.info("strategy_changed", new_strategy=strategy.name)

    def set_strategy_by_type(self, strategy_type: StrategyType):
        self.strategy = StrategyFactory.create(strategy_type=strategy_type)
        logger.info("strategy_change_by_type", strategy_type=strategy_type.value)

    def set_strategy_by_environment(self, enironment: Environment):
        self.strategy = StrategyFactory.create(environment=enironment)
        logger.info("strategy_changed_by_environment", enironment=enironment.value)

    def get_decision_summary(self, decision: DecisionResult) -> dict:
        return {
            "should_auto_fix": decision.should_auto_fix,
            "confidence": f"{decision.confidence:.2f}",
            "strategy": decision.strategy_name,
            "requiers_approval": decision.requires_approval,
            "escalate": decision.escalate,
            "reason": decision.reason,
            "warnings": decision.warnings,
        }