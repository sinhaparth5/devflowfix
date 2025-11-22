# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import structlog

from app.core.models.incident import Incident
from app.core.enums import IncidentSource, Outcome
from app.adapters.ai.nvidia import EmbeddingAdapter
from app.adapters.database.postgres.repositories.
from app.adapters.database.postgres.models import IncidentTable