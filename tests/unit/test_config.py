"""Test cases for configuration management."""

import os
from unittest.mock import patch

import pytest


class TestSettings:
    """Test Settings class configuration loading."""

    def test_settings_loads_defaults(self):
        """Test that settings loads with default values."""
        from app.core.config import Settings

        settings = Settings()

        assert settings.app_name == "paimon-backend"
        assert settings.debug is False
        assert settings.api_v1_prefix == "/api/v1"

    def test_settings_environment_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {"DEBUG": "true", "APP_NAME": "test-app"}):
            from importlib import reload
            from app.core import config
            reload(config)

            settings = config.Settings()

            assert settings.debug is True
            assert settings.app_name == "test-app"

    def test_database_url_construction(self):
        """Test database URL is properly constructed."""
        from app.core.config import Settings

        settings = Settings(
            db_host="localhost",
            db_port=5432,
            db_user="test",
            db_password="secret",
            db_name="testdb"
        )

        assert "postgresql" in settings.database_url
        assert "localhost" in settings.database_url
        assert "5432" in settings.database_url

    def test_redis_url_construction(self):
        """Test Redis URL is properly constructed."""
        from app.core.config import Settings

        settings = Settings(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0
        )

        assert "redis://" in settings.redis_url
        assert "localhost" in settings.redis_url


class TestEnvironmentValidation:
    """Test environment-specific validations."""

    def test_production_requires_secret_key(self):
        """Test that production environment requires a proper secret key."""
        from app.core.config import Settings

        # Should not raise with a proper secret key
        settings = Settings(
            environment="production",
            secret_key="a-very-long-secret-key-for-production-use"
        )
        assert settings.environment == "production"

    def test_development_allows_default_secret(self):
        """Test that development allows default secret key."""
        from app.core.config import Settings

        settings = Settings(environment="development")
        assert settings.environment == "development"
