"""Tests for reports API endpoints."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.reports import ExportFormat, ReportType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestListReports:
    """Tests for listing reports."""

    def test_list_reports_empty(self, client):
        """Test listing reports when empty."""
        response = client.get("/api/v1/reports/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_reports_with_type_filter(self, client):
        """Test listing reports with type filter."""
        response = client.get("/api/v1/reports/", params={"report_type": "DAILY"})
        assert response.status_code == 200

    def test_list_reports_with_date_filter(self, client):
        """Test listing reports with date filter."""
        response = client.get(
            "/api/v1/reports/",
            params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
        )
        assert response.status_code == 200

    def test_list_reports_with_limit(self, client):
        """Test listing reports with limit."""
        response = client.get("/api/v1/reports/", params={"limit": 10})
        assert response.status_code == 200


class TestGenerateReport:
    """Tests for report generation."""

    def test_generate_daily_report(self, client):
        """Test generating daily report."""
        response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data
        assert data["status"] == "COMPLETED"
        assert "download_url" in data

    def test_generate_daily_report_missing_date(self, client):
        """Test generating daily report without date."""
        response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "DAILY", "format": "PDF"},
        )
        assert response.status_code == 400
        assert "report_date required" in response.json()["detail"]

    def test_generate_weekly_report(self, client):
        """Test generating weekly report."""
        response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "WEEKLY",
                "report_date": "2024-06-10",
                "format": "EXCEL",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data

    def test_generate_weekly_report_missing_date(self, client):
        """Test generating weekly report without date."""
        response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "WEEKLY", "format": "PDF"},
        )
        assert response.status_code == 400
        assert "report_date" in response.json()["detail"]

    def test_generate_monthly_report(self, client):
        """Test generating monthly report."""
        response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "MONTHLY",
                "year": 2024,
                "month": 6,
                "format": "JSON",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data

    def test_generate_monthly_report_missing_params(self, client):
        """Test generating monthly report without year/month."""
        response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "MONTHLY", "format": "PDF"},
        )
        assert response.status_code == 400
        assert "year and month required" in response.json()["detail"]


class TestGetReport:
    """Tests for getting report metadata."""

    def test_get_report(self, client):
        """Test getting report metadata."""
        # First generate a report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Then get its metadata
        response = client.get(f"/api/v1/reports/{report_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] == report_id
        assert data["report_type"] == "DAILY"

    def test_get_nonexistent_report(self, client):
        """Test getting nonexistent report."""
        response = client.get("/api/v1/reports/NONEXISTENT")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestDownloadReport:
    """Tests for downloading reports."""

    def test_download_report_pdf(self, client):
        """Test downloading report as PDF."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Download
        response = client.get(f"/api/v1/reports/download/{report_id}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]

    def test_download_report_json(self, client):
        """Test downloading report as JSON."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "JSON",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Download
        response = client.get(f"/api/v1/reports/download/{report_id}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_download_report_csv(self, client):
        """Test downloading report as CSV."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "CSV",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Download
        response = client.get(f"/api/v1/reports/download/{report_id}")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_download_report_excel(self, client):
        """Test downloading report as Excel."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "EXCEL",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Download
        response = client.get(f"/api/v1/reports/download/{report_id}")
        assert response.status_code == 200
        assert "spreadsheet" in response.headers["content-type"]

    def test_download_with_format_override(self, client):
        """Test downloading with format override."""
        # Generate as PDF
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Download as JSON
        response = client.get(
            f"/api/v1/reports/download/{report_id}",
            params={"format": "JSON"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_download_nonexistent_report(self, client):
        """Test downloading nonexistent report."""
        response = client.get("/api/v1/reports/download/NONEXISTENT")
        assert response.status_code == 404


class TestDeleteReport:
    """Tests for deleting reports."""

    def test_delete_report(self, client):
        """Test deleting report."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Delete
        response = client.delete(f"/api/v1/reports/{report_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify deleted
        get_response = client.get(f"/api/v1/reports/{report_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_report(self, client):
        """Test deleting nonexistent report."""
        response = client.delete("/api/v1/reports/NONEXISTENT")
        assert response.status_code == 404


class TestGetReportData:
    """Tests for getting report data."""

    def test_get_report_data(self, client):
        """Test getting report data as JSON."""
        # Generate report
        gen_response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "DAILY",
                "report_date": "2024-06-15",
                "format": "PDF",
            },
        )
        report_id = gen_response.json()["report_id"]

        # Get data
        response = client.get(f"/api/v1/reports/{report_id}/data")
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert "report_date" in data
        assert "opening_nav" in data

    def test_get_report_data_nonexistent(self, client):
        """Test getting data for nonexistent report."""
        response = client.get("/api/v1/reports/NONEXISTENT/data")
        assert response.status_code == 404
