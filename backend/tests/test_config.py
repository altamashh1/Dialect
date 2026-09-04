"""Deployment configuration: URL normalisation and the production guard."""
import pytest

from app.config import Settings, check_production_readiness


def make_settings(**kwargs) -> Settings:
    """Settings built from defaults only.

    `_env_file=None` matters: without it pydantic-settings loads the
    developer's real backend/.env, so assertions about *default* values would
    pass or fail depending on whose machine the suite runs on.
    """
    return Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db"],
)
def test_managed_postgres_urls_are_normalised(given):
    """Render hands out `postgres://`, which SQLAlchemy 2 refuses to parse."""
    s = make_settings(database_url=given)
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_sqlite_url_is_left_alone():
    assert make_settings(database_url="sqlite:///./app.db").database_url == "sqlite:///./app.db"


def test_cors_origins_parse_into_a_list():
    s = make_settings(cors_origins="https://a.vercel.app, https://b.com ,")
    assert s.cors_origin_list == ["https://a.vercel.app", "https://b.com"]


def test_development_config_is_never_blocked():
    s = make_settings(environment="development")
    assert check_production_readiness(s) == []


def test_production_rejects_development_defaults():
    problems = check_production_readiness(make_settings(environment="production"))
    joined = " ".join(problems)
    assert "JWT_SECRET" in joined
    assert "STORAGE_BACKEND" in joined  # ephemeral disk would lose every upload
    assert "SQLite" in joined
    assert "GEMINI_API_KEY" in joined


def test_production_rejects_a_short_secret():
    s = make_settings(environment="production", jwt_secret="too-short")
    assert any("32 characters" in p for p in check_production_readiness(s))


def test_production_rejects_localhost_cors():
    s = make_settings(environment="production", cors_origins="http://localhost:5173")
    assert any("localhost" in p for p in check_production_readiness(s))


def test_fully_configured_production_passes():
    s = make_settings(
        environment="production",
        jwt_secret="x" * 48,
        storage_backend="s3",
        s3_bucket="my-bucket",
        database_url="postgres://u:p@host/db",
        gemini_api_key="key",
        cors_origins="https://app.vercel.app",
    )
    assert check_production_readiness(s) == []
