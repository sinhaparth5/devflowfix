# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""PDF export service for incidents and analytics reports."""

import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import structlog

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        PageBreak,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from app.adapters.database.postgres.models import IncidentTable

logger = structlog.get_logger(__name__)


class PDFExportService:
    """Service for exporting data to PDF format."""

    def __init__(self, export_dir: str = "/tmp/exports"):
        """
        Initialize PDF export service.

        Args:
            export_dir: Directory to store exported files
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError(
                "reportlab library is not installed. "
                "Install it with: pip install reportlab"
            )

        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)
        self.styles = getSampleStyleSheet()

        # Custom styles
        self.title_style = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=30,
            alignment=TA_CENTER,
        )

        self.heading_style = ParagraphStyle(
            "CustomHeading",
            parent=self.styles["Heading2"],
            fontSize=16,
            textColor=colors.HexColor("#2c3e50"),
            spaceAfter=12,
            spaceBefore=12,
        )

    def export_incidents(
        self,
        incidents: List[IncidentTable],
        filename: Optional[str] = None,
        title: str = "Incident Report",
    ) -> tuple[str, int]:
        """
        Export incidents to PDF file.

        Args:
            incidents: List of incidents to export
            filename: Optional custom filename
            title: Report title

        Returns:
            Tuple of (file_path, file_size)
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"incidents_report_{timestamp}.pdf"

        file_path = os.path.join(self.export_dir, filename)

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter)
            story = []

            # Title
            story.append(Paragraph(title, self.title_style))
            story.append(Spacer(1, 0.2 * inch))

            # Summary
            story.append(Paragraph("Summary", self.heading_style))
            summary_data = [
                ["Metric", "Value"],
                ["Total Incidents", str(len(incidents))],
                ["Report Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
            ]

            # Count by severity
            severity_counts = {}
            for incident in incidents:
                severity_counts[incident.severity] = severity_counts.get(incident.severity, 0) + 1

            for severity, count in sorted(severity_counts.items()):
                summary_data.append([f"{severity.capitalize()} Severity", str(count)])

            summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
            summary_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ])
            )
            story.append(summary_table)
            story.append(Spacer(1, 0.4 * inch))

            # Incidents table
            story.append(Paragraph("Incident Details", self.heading_style))

            # Prepare incidents data
            incidents_data = [["ID", "Source", "Severity", "Failure Type", "Outcome", "Created"]]

            for incident in incidents[:50]:  # Limit to 50 for PDF size
                incidents_data.append([
                    incident.incident_id[:12] + "...",
                    incident.source[:15],
                    incident.severity,
                    (incident.failure_type or "N/A")[:15],
                    (incident.outcome or "pending")[:12],
                    incident.created_at.strftime("%Y-%m-%d") if incident.created_at else "N/A",
                ])

            incidents_table = Table(incidents_data, colWidths=[1.2 * inch, 1 * inch, 0.8 * inch, 1.2 * inch, 0.9 * inch, 1 * inch])
            incidents_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                ])
            )
            story.append(incidents_table)

            if len(incidents) > 50:
                story.append(Spacer(1, 0.2 * inch))
                story.append(
                    Paragraph(
                        f"<i>Note: Showing first 50 of {len(incidents)} incidents</i>",
                        self.styles["Italic"],
                    )
                )

            # Build PDF
            doc.build(story)

            file_size = os.path.getsize(file_path)

            logger.info(
                "pdf_export_completed",
                file_path=file_path,
                file_size=file_size,
                incidents_count=len(incidents),
            )

            return file_path, file_size

        except Exception as e:
            logger.error("pdf_export_failed", error=str(e), file_path=file_path)
            raise

    def export_analytics(
        self,
        data: Dict[str, Any],
        filename: Optional[str] = None,
        title: str = "Analytics Report",
    ) -> tuple[str, int]:
        """
        Export analytics data to PDF file.

        Args:
            data: Analytics data dictionary
            filename: Optional custom filename
            title: Report title

        Returns:
            Tuple of (file_path, file_size)
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"analytics_report_{timestamp}.pdf"

        file_path = os.path.join(self.export_dir, filename)

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter)
            story = []

            # Title
            story.append(Paragraph(title, self.title_style))
            story.append(Spacer(1, 0.2 * inch))

            # Overview section
            story.append(Paragraph("Overview", self.heading_style))
            overview_data = [["Metric", "Value"]]

            if "total_incidents" in data:
                overview_data.append(["Total Incidents", str(data["total_incidents"])])
            if "resolved_incidents" in data:
                overview_data.append(["Resolved Incidents", str(data["resolved_incidents"])])
            if "success_rate" in data:
                overview_data.append(["Success Rate", f"{data['success_rate']:.2f}%"])
            if "average_resolution_time_seconds" in data and data["average_resolution_time_seconds"]:
                minutes = round(data["average_resolution_time_seconds"] / 60, 2)
                overview_data.append(["Avg Resolution Time", f"{minutes} minutes"])

            overview_data.append(["Report Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])

            overview_table = Table(overview_data, colWidths=[3 * inch, 2.5 * inch])
            overview_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ])
            )
            story.append(overview_table)
            story.append(Spacer(1, 0.3 * inch))

            # Breakdown by source
            if "incidents_by_source" in data and data["incidents_by_source"]:
                story.append(Paragraph("Breakdown by Source", self.heading_style))
                source_data = [["Source", "Count"]]
                for source, count in sorted(data["incidents_by_source"].items(), key=lambda x: x[1], reverse=True):
                    source_data.append([source, str(count)])

                source_table = Table(source_data, colWidths=[3 * inch, 1.5 * inch])
                source_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ])
                )
                story.append(source_table)
                story.append(Spacer(1, 0.3 * inch))

            # Breakdown by severity
            if "incidents_by_severity" in data and data["incidents_by_severity"]:
                story.append(Paragraph("Breakdown by Severity", self.heading_style))
                severity_data = [["Severity", "Count"]]
                for severity, count in sorted(data["incidents_by_severity"].items(), key=lambda x: x[1], reverse=True):
                    severity_data.append([severity, str(count)])

                severity_table = Table(severity_data, colWidths=[3 * inch, 1.5 * inch])
                severity_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ])
                )
                story.append(severity_table)
                story.append(Spacer(1, 0.3 * inch))

            # Breakdown by failure type
            if "incidents_by_failure_type" in data and data["incidents_by_failure_type"]:
                story.append(Paragraph("Breakdown by Failure Type", self.heading_style))
                failure_data = [["Failure Type", "Count"]]
                for failure_type, count in sorted(data["incidents_by_failure_type"].items(), key=lambda x: x[1], reverse=True):
                    failure_data.append([failure_type, str(count)])

                failure_table = Table(failure_data, colWidths=[3 * inch, 1.5 * inch])
                failure_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ])
                )
                story.append(failure_table)

            # Build PDF
            doc.build(story)

            file_size = os.path.getsize(file_path)

            logger.info(
                "analytics_pdf_export_completed",
                file_path=file_path,
                file_size=file_size,
            )

            return file_path, file_size

        except Exception as e:
            logger.error("analytics_pdf_export_failed", error=str(e), file_path=file_path)
            raise
