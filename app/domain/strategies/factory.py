# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
import structlog

from app.domain.strategies.base import BaseStrategy
from app.domain.strategies.conservative import ConservativeStrategy
from app.domain.strategies.slack_first import SlackFirstStrategy
from app.domain.strategies.hybrid import HybridStrategy
from app.domain.strategies.vector_db import VectorDBStrategy
from app.core.enums import Environment, StrategyType

logger = structlog.get_logger(__name__)

class StrategyFactory:
    _strategies = {
        StrategyType.CONSERVATIVE: ConservativeStrategy,
        StrategyType.SLACK_FIRST: SlackFirstStrategy,
        StrategyType.HYBRID: HybridStrategy,
        StrategyType.VECTOR_DB: VectorDBStrategy,
        StrategyType.AGGRESSIVE: SlackFirstStrategy,
    }

    @classmethod
    def create(
        cls,
        strategy_type: Optional[StrategyType] = None,
        environment: Optional[Environment] = None,
    ) -> BaseStrategy:
        if strategy_type:
            strategy_class = cls._strategies.get(strategy_type)
            if not strategy_class:
                logger.warning(
                    "unknown_strategy_type",
                    strategy_type=strategy_type,
                    fallback="hybrid",
                )
                strategy_class = HybridStrategy
            
            strategy = strategy_class()
            logger.info(
                "strategy_created",
                strategy=strategy.name,
                explicit=True,
            )
            return strategy
        
        if environment:
            strategy = cls._select_by_environment(environment)
        else:
            strategy = HybridStrategy()

        logger.info(
            "strategy_created",
            strategy=strategy.name,
            environment=environment.value if environment else None,
            auto_selected=True,
        )

        return strategy
    
    @classmethod
    def _select_by_environment(cls, environment: Environment) -> BaseStrategy:
        mapping = {
            Environment.PRODUCTION: ConservativeStrategy,
            Environment.STAGING: HybridStrategy,
            Environment.DEVELOPMENT: SlackFirstStrategy,
            Environment.TEST: SlackFirstStrategy,
        }

        strategy_class = mapping.get(environment, HybridStrategy)
        return strategy_class()
    
    @classmethod
    def get_available_strategies(cls) -> list[str]:
        return [st.value for st in StrategyType]
    
    @classmethod
    def get_strategy_info(cls, strategy_type: StrategyType) -> dict:
        strategy_class = cls._strategies.get(strategy_type)
        if not strategy_class:
            return {}
        
        temp_instance = strategy_class()

        return {
            "name": temp_instance.name,
            "min_confidence": temp_instance.min_confidence,
            "max_blast_radius": temp_instance.max_blast_radius,
            "enable_approval_flow": temp_instance.enable_approval_flow,
        }
