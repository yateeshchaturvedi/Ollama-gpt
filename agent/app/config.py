"""Application configuration using pydantic-settings.

All settings are read from environment variables with sensible defaults.
Bad values raise a clear ValidationError at startup rather than crashing mid-run.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


import os

# Find the project root directory containing the .env file
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
_env_file_path = os.path.join(_project_root, ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file_path,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


    # ── LLM Provider (Phase 2 ready) ────────────────────────────────────────
    llm_provider: Literal["gemini", "openai", "anthropic", "ollama"] = "ollama"

    # Gemini (Google AI)
    google_api_key: str = ""
    google_model: str = "gemini-1.5-pro"

    # OpenAI (future)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Anthropic / Claude (future)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # ── Ollama (current, removed in Phase 2) ────────────────────────────────
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_timeout_seconds: int = Field(default=60, ge=1)
    ollama_retries: int = Field(default=3, ge=1, le=10)

    # ── Agent Behaviour ──────────────────────────────────────────────────────
    max_tool_steps: int = Field(default=5, ge=1, le=20)
    max_history: int = Field(default=12, ge=2, le=100)

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Security ─────────────────────────────────────────────────────────────
    safe_workspace_root: str = "/app"
    allowed_shell_prefixes: str = "ls,dir,pwd,echo,cat,type"
    tool_rate_limit_count: int = Field(default=60, ge=1)
    tool_rate_limit_window_seconds: int = Field(default=60, ge=5)
    tool_audit_log_path: str = "logs/tool_audit.log"
    tool_audit_log_max_bytes: int = Field(default=10_485_760, ge=102_400)  # 10 MB default
    tool_audit_log_backup_count: int = Field(default=3, ge=0, le=20)
    dangerous_actions_require_confirmation: bool = True
    dangerous_confirmation_token: str = "CONFIRM"
    max_shell_output_chars: int = Field(default=8_000, ge=500)
    allowed_origins: str = ""

    # ── Database & Auth ──────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/devops_agent"
    db_encryption_key: str = Field(min_length=32)
    jwt_secret_key: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=30, ge=1)

    # GitHub OAuth (for portal login/onboarding only)
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"

    # ── SMTP / Email ─────────────────────────────────────────────────────────
    smtp_server: str = ""
    smtp_port: int = Field(default=587)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@devops-agent.local"
    frontend_url: str = "http://localhost:3000"

    # ── GitHub ───────────────────────────────────────────────────────────────
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    github_monitor_repos: str = ""
    github_alert_channel: str = ""
    github_alert_poll_seconds: int = Field(default=120, ge=30)
    github_pr_monitor_repos: str = ""
    github_pr_alert_channel: str = ""
    github_pr_poll_seconds: int = Field(default=180, ge=30)
    github_digest_repos: str = ""
    github_digest_channel: str = ""
    github_digest_hour: int = Field(default=9, ge=0, le=23)
    github_digest_minute: int = Field(default=0, ge=0, le=59)
    github_tz_offset_minutes: int = Field(default=330)

    # ── Jenkins ──────────────────────────────────────────────────────────────
    jenkins_url: str = ""
    jenkins_user: str = ""
    jenkins_api_token: str = ""
    jenkins_monitor_jobs: str = ""
    jenkins_alert_channel: str = ""
    jenkins_poll_seconds: int = Field(default=180, ge=30)

    # ── Azure DevOps ─────────────────────────────────────────────────────────
    azdo_org_url: str = ""
    azdo_pat: str = ""
    azdo_monitor_pipelines: str = ""
    azdo_alert_channel: str = ""
    azdo_poll_seconds: int = Field(default=180, ge=30)

    # ── GitLab ───────────────────────────────────────────────────────────────
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_monitor_projects: str = ""
    gitlab_alert_channel: str = ""
    gitlab_poll_seconds: int = Field(default=180, ge=30)

    # ── Slack ─────────────────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_allowed_channel: str = ""
    slack_require_mention: bool = True
    max_slack_reply_chars: int = Field(default=38_000, ge=1_000)
    monitor_state_path: str = "/workspace/monitor_state.json"

    # ── Validators ───────────────────────────────────────────────────────────
    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = str(v).strip().upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got '{v}'")
        return upper

    @field_validator("dangerous_confirmation_token", mode="before")
    @classmethod
    def warn_default_token(cls, v: str) -> str:
        # Validation only; runtime warning is emitted by security.py at startup.
        return str(v).strip()

    # ── Convenience helpers ──────────────────────────────────────────────────
    @property
    def ollama_url(self) -> str:
        """Backward-compatible alias used by the Ollama client."""
        return self.ollama_host

    def github_monitor_repos_list(self) -> list[str]:
        return [r.strip() for r in self.github_monitor_repos.split(",") if r.strip()]

    def github_pr_monitor_repos_list(self) -> list[str]:
        return [r.strip() for r in self.github_pr_monitor_repos.split(",") if r.strip()]

    def github_digest_repos_list(self) -> list[str]:
        return [r.strip() for r in self.github_digest_repos.split(",") if r.strip()]

    def jenkins_monitor_jobs_list(self) -> list[str]:
        return [j.strip() for j in self.jenkins_monitor_jobs.split(",") if j.strip()]

    def azdo_monitor_pipelines_list(self) -> list[str]:
        return [p.strip() for p in self.azdo_monitor_pipelines.split(",") if p.strip()]

    def gitlab_monitor_projects_list(self) -> list[str]:
        return [p.strip() for p in self.gitlab_monitor_projects.split(",") if p.strip()]

    def allowed_shell_prefixes_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_shell_prefixes.split(",") if p.strip()]


settings = Settings()
