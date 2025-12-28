# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""CSV export service for incidents and analytics data."""

import csv
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from io import StringIO
import structlog

from app.adapters.database.postgres.models import IncidentTable

logger = structlog.get_logger(__name__)


class CSVExportService:
    """Service for exporting data to CSV format."""

    def __init__(self, export_dir: str = "/tmp/exports"):
        """
        Initialize CSV export service.

        Args:
            export_dir: Directory to store exported files
        """
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def export_incidents(
        self,
        incidents: List[IncidentTable],
        filename: Optional[str] = None,
    ) -> tuple[str, int]:
        """
        Export incidents to CSV file.

        Args:
            incidents: List of incidents to export
            filename: Optional custom filename

        Returns:
            Tuple of (file_path, file_size)
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"incidents_export_{timestamp}.csv"

        file_path = os.path.join(self.export_dir, filename)

        # Define CSV columns
        fieldnames = [
            "incident_id",
            "timestamp",
            "source",
            "severity",
            "failure_type",
            "error_message",
            "root_cause",
            "confidence",
            "outcome",
            "outcome_message",
            "resolution_time_seconds",
            "remediation_executed",
            "created_at",
            "resolved_at",
            "repository",
            "namespace",
            "service",
        ]

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for incident in incidents:
                    # Extract context fields
                    context = incident.context or {}
                    repository = context.get("repository", "")
                    namespace = context.get("namespace", "")
                    service = context.get("service", "")

                    row = {
                        "incident_id": incident.incident_id,
                        "timestamp": incident.timestamp.isoformat() if incident.timestamp else "",
                        "source": incident.source,
                        "severity": incident.severity,
                        "failure_type": incident.failure_type or "",
                        "error_message": (incident.error_message or "")[:500],  # Truncate for CSV
                        "root_cause": (incident.root_cause or "")[:500],
                        "confidence": incident.confidence,
                        "outcome": incident.outcome or "",
                        "outcome_message": (incident.outcome_message or "")[:200],
                        "resolution_time_seconds": incident.resolution_time_seconds,
                        "remediation_executed": incident.remediation_executed,
                        "created_at": incident.created_at.isoformat() if incident.created_at else "",
                        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else "",
                        "repository": repository,
                        "namespace": namespace,
                        "service": service,
                    }
                    writer.writerow(row)

            file_size = os.path.getsize(file_path)

            logger.info(
                "csv_export_completed",
                file_path=file_path,
                file_size=file_size,
                incidents_count=len(incidents),
            )

            return file_path, file_size

        except Exception as e:
            logger.error("csv_export_failed", error=str(e), file_path=file_path)
            raise

    def export_analytics(
        self,
        data: Dict[str, Any],
        filename: Optional[str] = None,
    ) -> tuple[str, int]:
        """
        Export analytics data to CSV file.

        Args:
            data: Analytics data dictionary
            filename: Optional custom filename

        Returns:
            Tuple of (file_path, file_size)
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"analytics_export_{timestamp}.csv"

        file_path = os.path.join(self.export_dir, filename)

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)

                # Write summary statistics
                writer.writerow(["Analytics Summary"])
                writer.writerow([])
                writer.writerow(["Metric", "Value"])

                # Total incidents
                if "total_incidents" in data:
                    writer.writerow(["Total Incidents", data["total_incidents"]])

                # Success metrics
                if "resolved_incidents" in data:
                    writer.writerow(["Resolved Incidents", data["resolved_incidents"]])
                if "success_rate" in data:
                    writer.writerow(["Success Rate (%)", data["success_rate"]])

                # Resolution time
                if "average_resolution_time_seconds" in data:
                    avg_time = data["average_resolution_time_seconds"]
                    if avg_time:
                        writer.writerow(["Average Resolution Time (seconds)", avg_time])
                        writer.writerow(["Average Resolution Time (minutes)", round(avg_time / 60, 2)])

                writer.writerow([])

                # Breakdown by source
                if "incidents_by_source" in data:
                    writer.writerow(["Incidents by Source"])
                    writer.writerow(["Source", "Count"])
                    for source, count in data["incidents_by_source"].items():
                        writer.writerow([source, count])
                    writer.writerow([])

                # Breakdown by severity
                if "incidents_by_severity" in data:
                    writer.writerow(["Incidents by Severity"])
                    writer.writerow(["Severity", "Count"])
                    for severity, count in data["incidents_by_severity"].items():
                        writer.writerow([severity, count])
                    writer.writerow([])

                # Breakdown by failure type
                if "incidents_by_failure_type" in data:
                    writer.writerow(["Incidents by Failure Type"])
                    writer.writerow(["Failure Type", "Count"])
                    for failure_type, count in data["incidents_by_failure_type"].items():
                        writer.writerow([failure_type, count])

            file_size = os.path.getsize(file_path)

            logger.info(
                "analytics_csv_export_completed",
                file_path=file_path,
                file_size=file_size,
            )

            return file_path, file_size

        except Exception as e:
            logger.error("analytics_csv_export_failed", error=str(e), file_path=file_path)
            raise

    def export_to_string(self, incidents: List[IncidentTable]) -> str:
        """
        Export incidents to CSV string (for small exports).

        Args:
            incidents: List of incidents to export

        Returns:
            CSV content as string
        """
        output = StringIO()
        fieldnames = [
            "incident_id",
            "timestamp",
            "source",
            "severity",
            "failure_type",
            "error_message",
            "confidence",
            "outcome",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for incident in incidents:
            row = {
                "incident_id": incident.incident_id,
                "timestamp": incident.timestamp.isoformat() if incident.timestamp else "",
                "source": incident.source,
                "severity": incident.severity,
                "failure_type": incident.failure_type or "",
                "error_message": (incident.error_message or "")[:200],
                "confidence": incident.confidence,
                "outcome": incident.outcome or "",
            }
            writer.writerow(row)

        return output.getvalue()
