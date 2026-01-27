"""Tests for health and root endpoints."""

import pytest
from unittest.mock import AsyncMock


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, test_client, mock_db):
        """Test health check when database is healthy."""
        mock_db.health_check = AsyncMock(return_value=True)

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, test_client, mock_db):
        """Test health check when database is unhealthy."""
        mock_db.health_check = AsyncMock(return_value=False)

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"

    @pytest.mark.asyncio
    async def test_health_check_no_db(self, test_client):
        """Test health check when database is not initialized."""
        from src.api import dependencies
        dependencies.db_bridge = None

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"


class TestRootEndpoint:
    """Tests for / root endpoint."""

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns service info."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data
        assert data["health"] == "/health"
