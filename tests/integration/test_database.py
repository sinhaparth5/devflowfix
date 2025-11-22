# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.adapters.database.postgres.models import (
    IncidentTable,
    FeedbackTable,
    RemediationHistoryTable,
    MetricTable,
    ConfigTable,
)
from app.core.enums import (
    IncidentSource,
    Severity,
    Outcome,
    FailureType,
    Fixability,
)


@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def test_session(test_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_incident_data():
    return {
        "incident_id": "inc_test123",
        "timestamp": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source": IncidentSource.GITHUB.value,
        "severity": Severity.HIGH.value,
        "failure_type": FailureType.BUILD_FAILURE.value,
        "error_log": "Error: Build failed\nStep 3/10: npm install failed",
        "error_message": "npm install failed",
        "context": {
            "repository": "org/repo",
            "workflow": "CI",
            "branch": "main",
            "run_id": 12345,
        },
        "remediation_executed": False,
        "raw_payload": {},
        "tags": ["ci", "npm"],
    }


@pytest.fixture
def sample_incident_table(test_session, sample_incident_data):
    incident = IncidentTable(**sample_incident_data)
    test_session.add(incident)
    test_session.commit()
    test_session.refresh(incident)
    return incident


class TestIncidentTableCRUD:
    
    def test_create_incident(self, test_session, sample_incident_data):
        incident = IncidentTable(**sample_incident_data)
        test_session.add(incident)
        test_session.commit()
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == sample_incident_data["incident_id"]
        ).first()
        
        assert result is not None
        assert result.incident_id == sample_incident_data["incident_id"]
        assert result.source == IncidentSource.GITHUB.value
        assert result.severity == Severity.HIGH.value
    
    def test_get_incident(self, test_session, sample_incident_table):
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == sample_incident_table.incident_id
        ).first()
        
        assert result is not None
        assert result.incident_id == sample_incident_table.incident_id
        assert result.error_log == sample_incident_table.error_log
    
    def test_get_incident_not_found(self, test_session):
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == "nonexistent_id"
        ).first()
        
        assert result is None
    
    def test_update_incident(self, test_session, sample_incident_table):
        sample_incident_table.outcome = Outcome.SUCCESS.value
        sample_incident_table.root_cause = "Transient network error"
        sample_incident_table.confidence = 0.92
        sample_incident_table.updated_at = datetime.utcnow()
        
        test_session.commit()
        test_session.refresh(sample_incident_table)
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == sample_incident_table.incident_id
        ).first()
        
        assert result.outcome == Outcome.SUCCESS.value
        assert result.root_cause == "Transient network error"
        assert result.confidence == 0.92
    
    def test_list_incidents(self, test_session):
        for i in range(5):
            incident = IncidentTable(
                incident_id=f"inc_list_{i}",
                timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                source=IncidentSource.GITHUB.value,
                severity=Severity.MEDIUM.value,
                error_log=f"Error {i}",
                remediation_executed=False,
                context={},
                raw_payload={},
                tags=[],
            )
            test_session.add(incident)
        test_session.commit()
        
        results = test_session.query(IncidentTable).all()
        
        assert len(results) == 5
    
    def test_list_incidents_with_filter(self, test_session):
        incident1 = IncidentTable(
            incident_id="inc_filter_1",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.GITHUB.value,
            severity=Severity.CRITICAL.value,
            error_log="Critical error",
            remediation_executed=False,
            context={},
            raw_payload={},
            tags=[],
        )
        incident2 = IncidentTable(
            incident_id="inc_filter_2",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.KUBERNETES.value,
            severity=Severity.LOW.value,
            error_log="Low error",
            remediation_executed=False,
            context={},
            raw_payload={},
            tags=[],
        )
        
        test_session.add(incident1)
        test_session.add(incident2)
        test_session.commit()
        
        results = test_session.query(IncidentTable).filter(
            IncidentTable.source == IncidentSource.GITHUB.value
        ).all()
        
        assert len(results) == 1
        assert results[0].source == IncidentSource.GITHUB.value
    
    def test_count_incidents(self, test_session):
        for i in range(3):
            incident = IncidentTable(
                incident_id=f"inc_count_{i}",
                timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                source=IncidentSource.GITHUB.value,
                severity=Severity.MEDIUM.value,
                error_log=f"Error {i}",
                remediation_executed=False,
                context={},
                raw_payload={},
                tags=[],
            )
            test_session.add(incident)
        test_session.commit()
        
        from sqlalchemy import func
        count = test_session.query(func.count(IncidentTable.incident_id)).scalar()
        
        assert count == 3
    
    def test_delete_incident(self, test_session, sample_incident_table):
        incident_id = sample_incident_table.incident_id
        
        test_session.delete(sample_incident_table)
        test_session.commit()
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id
        ).first()
        
        assert result is None
    
    def test_incident_with_outcome(self, test_session):
        incident = IncidentTable(
            incident_id="inc_outcome_test",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.GITHUB.value,
            severity=Severity.HIGH.value,
            error_log="Test error",
            outcome=Outcome.SUCCESS.value,
            confidence=0.95,
            resolution_time_seconds=120,
            remediation_executed=True,
            context={},
            raw_payload={},
            tags=[],
        )
        test_session.add(incident)
        test_session.commit()
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.outcome == Outcome.SUCCESS.value
        ).first()
        
        assert result is not None
        assert result.resolution_time_seconds == 120
    
    def test_incident_approval(self, test_session, sample_incident_table):
        sample_incident_table.approved_by = "test_user"
        sample_incident_table.approval_timestamp = datetime.utcnow()
        test_session.commit()
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == sample_incident_table.incident_id
        ).first()
        
        assert result.approved_by == "test_user"
        assert result.approval_timestamp is not None


class TestFeedbackTable:
    
    def test_create_feedback(self, test_session, sample_incident_table):
        feedback = FeedbackTable(
            feedback_id="fb_test1",
            incident_id=sample_incident_table.incident_id,
            helpful=True,
            comment="Great fix!",
            user="testuser",
            user_email="test@example.com",
            rating=5,
            created_at=datetime.utcnow(),
        )
        test_session.add(feedback)
        test_session.commit()
        
        result = test_session.query(FeedbackTable).filter(
            FeedbackTable.feedback_id == "fb_test1"
        ).first()
        
        assert result is not None
        assert result.helpful is True
        assert result.rating == 5
    
    def test_feedback_foreign_key(self, test_session, sample_incident_table):
        feedback = FeedbackTable(
            feedback_id="fb_fk_test",
            incident_id=sample_incident_table.incident_id,
            helpful=False,
            comment="Didn't work",
            created_at=datetime.utcnow(),
        )
        test_session.add(feedback)
        test_session.commit()
        
        result = test_session.query(FeedbackTable).filter(
            FeedbackTable.incident_id == sample_incident_table.incident_id
        ).first()
        
        assert result is not None
        assert result.incident_id == sample_incident_table.incident_id


class TestRemediationHistoryTable:
    
    def test_create_remediation_history(self, test_session, sample_incident_table):
        history = RemediationHistoryTable(
            history_id="hist_test1",
            incident_id=sample_incident_table.incident_id,
            attempt_number=1,
            action_type="github_rerun_workflow",
            executed_at=datetime.utcnow(),
            duration_seconds=45,
            success=True,
            outcome=Outcome.SUCCESS.value,
            message="Workflow rerun successful",
            executed_by="system",
            environment="dev",
            dry_run=False,
            pre_validation_passed=True,
            post_validation_passed=True,
            rollback_required=False,
            rollback_performed=False,
        )
        test_session.add(history)
        test_session.commit()
        
        result = test_session.query(RemediationHistoryTable).filter(
            RemediationHistoryTable.history_id == "hist_test1"
        ).first()
        
        assert result is not None
        assert result.success is True
        assert result.duration_seconds == 45
    
    def test_multiple_remediation_attempts(self, test_session, sample_incident_table):
        for i in range(3):
            history = RemediationHistoryTable(
                history_id=f"hist_multi_{i}",
                incident_id=sample_incident_table.incident_id,
                attempt_number=i + 1,
                action_type="k8s_restart_pod",
                executed_at=datetime.utcnow(),
                success=i == 2,
                outcome=Outcome.SUCCESS.value if i == 2 else Outcome.FAILED.value,
                environment="dev",
                dry_run=False,
                pre_validation_passed=True,
                post_validation_passed=i == 2,
                rollback_required=i != 2,
                rollback_performed=i != 2,
            )
            test_session.add(history)
        test_session.commit()
        
        results = test_session.query(RemediationHistoryTable).filter(
            RemediationHistoryTable.incident_id == sample_incident_table.incident_id
        ).order_by(RemediationHistoryTable.attempt_number).all()
        
        assert len(results) == 3
        assert results[0].attempt_number == 1
        assert results[2].success is True


class TestMetricTable:
    
    def test_create_metric(self, test_session):
        metric = MetricTable(
            metric_id="metric_test1",
            metric_name="incident_count",
            metric_type="counter",
            value=42.0,
            unit="count",
            labels={"source": "github"},
            timestamp=datetime.utcnow(),
        )
        test_session.add(metric)
        test_session.commit()
        
        result = test_session.query(MetricTable).filter(
            MetricTable.metric_id == "metric_test1"
        ).first()
        
        assert result is not None
        assert result.value == 42.0
        assert result.labels["source"] == "github"
    
    def test_query_metrics_by_name(self, test_session):
        for i in range(5):
            metric = MetricTable(
                metric_id=f"metric_query_{i}",
                metric_name="response_time",
                metric_type="gauge",
                value=100.0 + i * 10,
                unit="ms",
                labels={},
                timestamp=datetime.utcnow() - timedelta(minutes=i),
            )
            test_session.add(metric)
        test_session.commit()
        
        results = test_session.query(MetricTable).filter(
            MetricTable.metric_name == "response_time"
        ).all()
        
        assert len(results) == 5


class TestConfigTable:
    
    def test_create_config(self, test_session):
        config = ConfigTable(
            config_key="max_retries",
            config_value="3",
            value_type="int",
            description="Maximum retry attempts",
            category="remediation",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_secret=False,
            is_system=True,
        )
        test_session.add(config)
        test_session.commit()
        
        result = test_session.query(ConfigTable).filter(
            ConfigTable.config_key == "max_retries"
        ).first()
        
        assert result is not None
        assert result.config_value == "3"
        assert result.is_system is True
    
    def test_update_config(self, test_session):
        config = ConfigTable(
            config_key="timeout_seconds",
            config_value="30",
            value_type="int",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_secret=False,
            is_system=False,
        )
        test_session.add(config)
        test_session.commit()
        
        config.config_value = "60"
        config.updated_at = datetime.utcnow()
        config.updated_by = "admin"
        test_session.commit()
        
        result = test_session.query(ConfigTable).filter(
            ConfigTable.config_key == "timeout_seconds"
        ).first()
        
        assert result.config_value == "60"
        assert result.updated_by == "admin"


class TestAnalyticsQueries:
    
    @pytest.fixture
    def populated_db(self, test_session):
        for i in range(10):
            incident = IncidentTable(
                incident_id=f"inc_analytics_{i}",
                timestamp=datetime.utcnow() - timedelta(days=i),
                created_at=datetime.utcnow() - timedelta(days=i),
                updated_at=datetime.utcnow(),
                source=IncidentSource.GITHUB.value if i % 2 == 0 else IncidentSource.KUBERNETES.value,
                severity=Severity.HIGH.value if i % 3 == 0 else Severity.MEDIUM.value,
                failure_type=FailureType.BUILD_FAILURE.value,
                error_log=f"Error {i}",
                outcome=Outcome.SUCCESS.value if i % 2 == 0 else Outcome.FAILED.value,
                confidence=0.8 + (i * 0.02),
                resolution_time_seconds=60 + (i * 10) if i % 2 == 0 else None,
                remediation_executed=i % 2 == 0,
                context={"repository": f"org/repo{i}"},
                raw_payload={},
                tags=[],
            )
            test_session.add(incident)
        test_session.commit()
        return test_session
    
    def test_count_by_source(self, populated_db):
        from sqlalchemy import func
        
        results = populated_db.query(
            IncidentTable.source,
            func.count(IncidentTable.incident_id)
        ).group_by(IncidentTable.source).all()
        
        by_source = {source: count for source, count in results}
        
        assert IncidentSource.GITHUB.value in by_source
        assert IncidentSource.KUBERNETES.value in by_source
    
    def test_count_by_outcome(self, populated_db):
        from sqlalchemy import func
        
        results = populated_db.query(
            IncidentTable.outcome,
            func.count(IncidentTable.incident_id)
        ).group_by(IncidentTable.outcome).all()
        
        by_outcome = {outcome: count for outcome, count in results}
        
        assert Outcome.SUCCESS.value in by_outcome
        assert Outcome.FAILED.value in by_outcome
    
    def test_average_resolution_time(self, populated_db):
        from sqlalchemy import func
        
        avg_time = populated_db.query(
            func.avg(IncidentTable.resolution_time_seconds)
        ).filter(
            IncidentTable.outcome == Outcome.SUCCESS.value,
            IncidentTable.resolution_time_seconds.isnot(None)
        ).scalar()
        
        assert avg_time is not None
        assert avg_time > 0
    
    def test_success_rate(self, populated_db):
        from sqlalchemy import func
        
        total = populated_db.query(func.count(IncidentTable.incident_id)).scalar()
        successful = populated_db.query(func.count(IncidentTable.incident_id)).filter(
            IncidentTable.outcome == Outcome.SUCCESS.value
        ).scalar()
        
        success_rate = (successful / total * 100) if total > 0 else 0
        
        assert success_rate == 50.0
    
    def test_filter_by_date_range(self, populated_db):
        start_date = datetime.utcnow() - timedelta(days=5)
        
        results = populated_db.query(IncidentTable).filter(
            IncidentTable.created_at >= start_date
        ).all()
        
        assert len(results) <= 10
        for incident in results:
            assert incident.created_at >= start_date


class TestVectorOperations:
    
    def test_store_embedding_field(self, test_session):
        embedding = [0.1] * 768
        
        incident = IncidentTable(
            incident_id="inc_embed_test",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.GITHUB.value,
            severity=Severity.HIGH.value,
            error_log="Test error",
            embedding=embedding,
            remediation_executed=False,
            context={},
            raw_payload={},
            tags=[],
        )
        test_session.add(incident)
        test_session.commit()
        
        result = test_session.query(IncidentTable).filter(
            IncidentTable.incident_id == "inc_embed_test"
        ).first()
        
        assert result is not None
        assert result.embedding is not None
    
    def test_check_has_embedding(self, test_session):
        incident_with = IncidentTable(
            incident_id="inc_with_embed",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.GITHUB.value,
            severity=Severity.HIGH.value,
            error_log="Test",
            embedding=[0.1] * 768,
            remediation_executed=False,
            context={},
            raw_payload={},
            tags=[],
        )
        incident_without = IncidentTable(
            incident_id="inc_without_embed",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            source=IncidentSource.GITHUB.value,
            severity=Severity.HIGH.value,
            error_log="Test",
            embedding=None,
            remediation_executed=False,
            context={},
            raw_payload={},
            tags=[],
        )
        test_session.add(incident_with)
        test_session.add(incident_without)
        test_session.commit()
        
        with_embedding = test_session.query(IncidentTable).filter(
            IncidentTable.embedding.isnot(None)
        ).count()
        
        without_embedding = test_session.query(IncidentTable).filter(
            IncidentTable.embedding.is_(None)
        ).count()
        
        assert with_embedding >= 1
        assert without_embedding >= 1
    
    def test_get_incidents_without_embeddings(self, test_session):
        for i in range(3):
            incident = IncidentTable(
                incident_id=f"inc_no_embed_{i}",
                timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                source=IncidentSource.GITHUB.value,
                severity=Severity.MEDIUM.value,
                error_log=f"Error {i}",
                embedding=None,
                remediation_executed=False,
                context={},
                raw_payload={},
                tags=[],
            )
            test_session.add(incident)
        test_session.commit()
        
        results = test_session.query(IncidentTable).filter(
            IncidentTable.embedding.is_(None)
        ).limit(10).all()
        
        assert isinstance(results, list)
        assert len(results) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])