"""Report API endpoints."""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.reports import (
    ExportFormat,
    ReportGenerator,
    ReportType,
    StoredReport,
    get_report_generator,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# Request models
class GenerateReportRequest(BaseModel):
    """Request to generate a report."""

    report_type: ReportType = Field(..., description="Report type")
    report_date: date | None = Field(None, description="Report date (for daily)")
    year: int | None = Field(None, description="Year (for monthly)")
    month: int | None = Field(None, description="Month (for monthly)")
    format: ExportFormat = Field(default=ExportFormat.PDF, description="Format")


# Endpoints
@router.get("/", response_model=list[StoredReport])
async def list_reports(
    report_type: ReportType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=50, le=100),
) -> list[StoredReport]:
    """List generated reports.

    Args:
        report_type: Filter by type
        start_date: Filter by start date
        end_date: Filter by end date
        limit: Max reports
    """
    generator = get_report_generator()
    return generator.list_reports(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.post("/generate")
async def generate_report(request: GenerateReportRequest) -> dict[str, Any]:
    """Generate a report on-demand.

    Args:
        request: Generation request
    """
    generator = get_report_generator()

    if request.report_type == ReportType.DAILY:
        if not request.report_date:
            raise HTTPException(400, "report_date required for daily reports")
        report = generator.generate_daily_report(request.report_date, request.format)
    elif request.report_type == ReportType.WEEKLY:
        if not request.report_date:
            raise HTTPException(400, "report_date (week start) required")
        report = generator.generate_weekly_report(request.report_date, request.format)
    elif request.report_type == ReportType.MONTHLY:
        if not request.year or not request.month:
            raise HTTPException(400, "year and month required for monthly reports")
        report = generator.generate_monthly_report(request.year, request.month, request.format)
    else:
        raise HTTPException(400, f"Unsupported report type: {request.report_type}")

    return {
        "report_id": report.metadata.report_id,
        "status": report.metadata.status.value,
        "download_url": f"/api/v1/reports/download/{report.metadata.report_id}",
    }


@router.get("/{report_id}")
async def get_report(report_id: str) -> StoredReport:
    """Get report metadata.

    Args:
        report_id: Report ID
    """
    generator = get_report_generator()
    report = generator.get_report(report_id)

    if not report:
        raise HTTPException(404, "Report not found")

    return report


@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    format: ExportFormat = Query(default=None),
) -> Response:
    """Download report in specified format.

    Args:
        report_id: Report ID
        format: Override format (optional)
    """
    generator = get_report_generator()
    stored = generator.get_report(report_id)

    if not stored:
        raise HTTPException(404, "Report not found")

    export_format = format or stored.format
    data = generator.export_report(report_id, export_format)

    if not data:
        raise HTTPException(500, "Failed to export report")

    # Determine content type and filename
    content_types = {
        ExportFormat.PDF: "application/pdf",
        ExportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ExportFormat.CSV: "text/csv",
        ExportFormat.JSON: "application/json",
    }
    extensions = {
        ExportFormat.PDF: "pdf",
        ExportFormat.EXCEL: "xlsx",
        ExportFormat.CSV: "csv",
        ExportFormat.JSON: "json",
    }

    filename = f"{report_id}.{extensions[export_format]}"

    return Response(
        content=data,
        media_type=content_types[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{report_id}")
async def delete_report(report_id: str) -> dict[str, Any]:
    """Delete a report.

    Args:
        report_id: Report ID
    """
    generator = get_report_generator()

    if not generator.delete_report(report_id):
        raise HTTPException(404, "Report not found")

    return {"status": "deleted", "report_id": report_id}


@router.get("/{report_id}/data")
async def get_report_data(report_id: str) -> dict[str, Any]:
    """Get report data (JSON).

    Args:
        report_id: Report ID
    """
    generator = get_report_generator()
    data = generator.get_report_data(report_id)

    if not data:
        raise HTTPException(404, "Report not found")

    return data.model_dump()
