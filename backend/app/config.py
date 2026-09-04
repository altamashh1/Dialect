from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" or "production". Production refuses to start on insecure
    # defaults -- see check_production_readiness().
    environment: str = "development"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    sandbox_timeout_seconds: int = 10
    # Hard caps for the sandbox subprocess: memory (POSIX RLIMIT_DATA / Windows
    # Job Object process-memory limit) and the size of the result it may hand
    # back. Both bound memory the process actually uses rather than what it
    # reserves, so size this against expected peak RSS -- and leave the API
    # process its own headroom inside the instance's total RAM.
    sandbox_memory_mb: int = 1024
    sandbox_output_mb: int = 8
    max_upload_mb: int = 25

    # After a successful run, sanity-check the result (deterministic invariants +
    # an LLM critic pass) and attach a confidence level. Costs one extra LLM call.
    verify_answers: bool = True

    database_url: str = "sqlite:///./app.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Comma-separated browser origins allowed to call the API.
    cors_origins: str = "http://localhost:5173"

    # Public demo. Seeds a shared `demo` account (holding sample_sales.csv) at
    # startup and enables POST /api/auth/demo, so a visitor can try the app
    # without creating an account. Off by default: it is a deployment choice,
    # not something a local dev run should silently turn on.
    demo_mode: bool = False
    demo_login: str = "demo"
    demo_password: str = "demo1234"

    # Password used by seed_admin.py. Deliberately empty: the script refuses to
    # run without it, so an admin password is never committed to the repo.
    admin_password: str = ""

    # Storage: "local" (default, no config) or "s3" (AWS S3 / Supabase / MinIO)
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # set for Supabase Storage or MinIO; blank for AWS
    s3_region: str = "us-east-1"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Managed Postgres hands out `postgres://`, which SQLAlchemy 2 rejects."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()

INSECURE_JWT_SECRETS = {"dev-secret-change-me", "change-me-to-a-long-random-string", ""}


def check_production_readiness(s: Settings = settings) -> list[str]:
    """Return fatal misconfigurations. Empty list means the config is safe."""
    if not s.is_production:
        return []

    problems = []
    if s.jwt_secret in INSECURE_JWT_SECRETS:
        problems.append("JWT_SECRET is unset or still the development default")
    if len(s.jwt_secret) < 32:
        problems.append("JWT_SECRET is shorter than 32 characters")
    if s.storage_backend != "s3":
        problems.append(
            "STORAGE_BACKEND is not 's3'; container filesystems are ephemeral "
            "and uploads would be lost on every restart"
        )
    if s.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL still points at SQLite on an ephemeral disk")
    if not s.gemini_api_key:
        problems.append("GEMINI_API_KEY is not set")
    if "localhost" in s.cors_origins:
        problems.append("CORS_ORIGINS still contains localhost")
    return problems
