from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import (
    Integer, String, Boolean, DateTime, Numeric, Text, LargeBinary,
    ForeignKey, UniqueConstraint, Index, event, text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, INET, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ================================================================
# ENUMS
# ================================================================

class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"

class PlatformType(str, enum.Enum):
    github = "github"
    gitlab = "gitlab"
    jenkins = "jenkins"
    azure_devops = "azure_devops"

class LLMProvider(str, enum.Enum):
    gemini = "gemini"
    openai = "openai"
    anthropic = "anthropic"
    ollama = "ollama"

class OAuthProvider(str, enum.Enum):
    github = "github"
    google = "google"
    microsoft = "microsoft"

class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    streaming = "streaming"
    completed = "completed"
    failed = "failed"

class TestStatus(str, enum.Enum):
    ok = "ok"
    failed = "failed"
    untested = "untested"

class AuditSource(str, enum.Enum):
    agent = "agent"
    api = "api"
    monitor = "monitor"
    auth = "auth"
    admin = "admin"

# ================================================================
# MODELS
# ================================================================

class PlanTier(Base):
    __tablename__ = "plan_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_repos: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_credentials: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    allow_slack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_multi_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_audit_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price_usd_monthly: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0.00)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    plan_tier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plan_tiers.id"), nullable=False, default=1
    )
    plan_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    billing_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    billing_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    plan_tier: Mapped[PlanTier] = relationship("PlanTier")
    users: Mapped[List[User]] = relationship(
        "User", back_populates="organisation", cascade="all, delete-orphan"
    )
    repositories: Mapped[List[Repository]] = relationship(
        "Repository", back_populates="organisation", cascade="all, delete-orphan"
    )
    credentials: Mapped[List[PlatformCredential]] = relationship(
        "PlatformCredential", back_populates="organisation", cascade="all, delete-orphan"
    )
    llm_configs: Mapped[List[LLMProviderConfig]] = relationship(
        "LLMProviderConfig", back_populates="organisation", cascade="all, delete-orphan"
    )
    slack_config: Mapped[Optional[SlackConfig]] = relationship(
        "SlackConfig", back_populates="organisation", cascade="all, delete-orphan"
    )
    agent_settings: Mapped[Optional[AgentSettings]] = relationship(
        "AgentSettings", back_populates="organisation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_orgs_slug", "slug"),
        Index("idx_orgs_active", "is_active", postgresql_where=text("is_active = true")),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    
    email: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    role: Mapped[UserRole] = mapped_column(
        String, nullable=False, default=UserRole.viewer
    )
    
    can_access_admin_portal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_access_user_portal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_invited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invited_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="users")
    oauth_connections: Mapped[List[OAuthConnection]] = relationship(
        "OAuthConnection", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[List[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "email", name="users_org_id_email_key"),
        UniqueConstraint("org_id", "username", name="users_org_id_username_key"),
        Index("idx_users_org", "org_id"),
        Index("idx_users_email", "org_id", "email"),
        Index("idx_users_active", "org_id", "is_active", postgresql_where=text("is_active = true")),
        Index("idx_users_admin", "org_id", postgresql_where=text("role IN ('owner', 'admin') AND is_active = true")),
    )


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    
    provider: Mapped[OAuthProvider] = mapped_column(String, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    access_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    refresh_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="oauth_connections")

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="oauth_connections_provider_provider_user_id_key"),
        Index("idx_oauth_user", "user_id"),
        Index("idx_oauth_provider", "provider", "provider_user_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    family_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    portal: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    
    device_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    replaced_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_rt_token_hash", "token_hash", postgresql_where=text("is_revoked = false")),
        Index("idx_rt_family", "family_id"),
        Index("idx_rt_user_active", "user_id", "expires_at", postgresql_where=text("is_revoked = false")),
        Index("idx_rt_cleanup", "expires_at", postgresql_where=text("is_revoked = false")),
    )


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_vt_user_purpose", "user_id", "purpose", postgresql_where=text("used_at IS NULL")),
    )


class OrgInvite(Base):
    __tablename__ = "org_invites"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    
    invited_email: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_role: Mapped[UserRole] = mapped_column(
        String, nullable=False, default=UserRole.viewer
    )
    invite_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invite_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    
    invited_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_invites_org", "org_id", postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL")),
        Index("idx_invites_code", "invite_code", postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL")),
    )


class PlatformCredential(Base):
    __tablename__ = "platform_credentials"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    platform: Mapped[PlatformType] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    
    api_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_app_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gitlab_group_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jenkins_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    azure_organisation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    azure_project: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # ENCRYPTED SECRET
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_scopes: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=True, server_default=text("'{}'::text[]"))
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[TestStatus] = mapped_column(
        String, nullable=False, default=TestStatus.untested
    )
    last_test_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="credentials")
    repositories: Mapped[List[Repository]] = relationship("Repository", back_populates="credential")

    __table_args__ = (
        UniqueConstraint("org_id", "platform", "label", name="platform_credentials_org_id_platform_label_key"),
        Index("idx_creds_org", "org_id", "platform", postgresql_where=text("is_active = true")),
        Index("idx_creds_expiry", "token_expires_at", postgresql_where=text("token_expires_at IS NOT NULL AND is_active = true")),
    )


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_configs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    provider: Mapped[LLMProvider] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # ENCRYPTED SECRET
    api_key_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    api_key_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.70)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=8192)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_tool_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_history: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[TestStatus] = mapped_column(
        String, nullable=False, default=TestStatus.untested
    )
    last_test_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="llm_configs")

    __table_args__ = (
        UniqueConstraint("org_id", "provider", "label", name="llm_provider_configs_org_id_provider_label_key"),
        Index("idx_llm_one_default", "org_id", "provider", postgresql_where=text("is_default = true AND is_active = true"), unique=True),
    )


class SlackConfig(Base):
    __tablename__ = "slack_configs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    slack_workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slack_workspace_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # ENCRYPTED SECRETS
    bot_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    app_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    bot_token_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    app_token_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    default_alert_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    require_mention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_reply_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=38000)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[TestStatus] = mapped_column(
        String, nullable=False, default=TestStatus.untested
    )
    last_test_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="slack_config")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("platform_credentials.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    platform: Mapped[PlatformType] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_interval_secs: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    
    notify_slack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    slack_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_poll_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_poll_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="repositories")
    credential: Mapped[Optional[PlatformCredential]] = relationship("PlatformCredential", back_populates="repositories")
    analysis_results: Mapped[List[AnalysisResult]] = relationship("AnalysisResult", back_populates="repository")

    __table_args__ = (
        UniqueConstraint("org_id", "platform", "name", name="repositories_org_id_platform_name_key"),
        Index("idx_repos_org_active", "org_id", postgresql_where=text("is_active = true")),
        Index("idx_repos_credential", "credential_id", postgresql_where=text("is_active = true")),
        Index("idx_repos_poll_due", "last_polled_at", postgresql_where=text("is_active = true AND monitor_enabled = true")),
    )


class AgentSettings(Base):
    __tablename__ = "agent_settings"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    dangerous_actions_require_confirm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmation_token: Mapped[str] = mapped_column(Text, nullable=False, default="CONFIRM")
    safe_workspace_root: Mapped[str] = mapped_column(Text, nullable=False, default="/app")
    allowed_shell_prefixes: Mapped[List[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY['ls','dir','pwd','echo','cat','type']::text[]")
    )
    max_shell_output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=8000)
    
    tool_rate_limit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    tool_rate_limit_window_secs: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    
    log_level: Mapped[str] = mapped_column(Text, nullable=False, default="INFO")
    audit_log_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=text("now()")
    )

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="agent_settings")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    repo_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    platform: Mapped[Optional[PlatformType]] = mapped_column(String, nullable=True)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    job_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_event: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    log_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_log_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    log_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    analysis_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    llm_config_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("llm_provider_configs.id", ondelete="SET NULL"), nullable=True
    )
    llm_provider: Mapped[Optional[LLMProvider]] = mapped_column(String, nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[AnalysisStatus] = mapped_column(
        String, nullable=False, default=AnalysisStatus.pending
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    user_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    repository: Mapped[Optional[Repository]] = relationship("Repository", back_populates="analysis_results")

    __table_args__ = (
        Index("idx_analysis_org_recent", "org_id", text("created_at DESC")),
        Index("idx_analysis_repo", "org_id", "repo_id", text("created_at DESC")),
        Index("idx_analysis_active", "org_id", "status", postgresql_where=text("status IN ('pending', 'streaming')")),
        Index("idx_analysis_log_hash", "org_id", "log_hash", postgresql_where=text("log_hash IS NOT NULL")),
    )


class SeenFailure(Base):
    __tablename__ = "seen_failures"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    repo_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    
    platform: Mapped[PlatformType] = mapped_column(String, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    
    analysis_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="SET NULL"), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("org_id", "platform", "repo_name", "run_id", name="seen_failures_org_platform_repo_run_key"),
        Index("idx_seen_failures_lookup", "org_id", "platform", "repo_name"),
        Index("idx_seen_failures_recent", "org_id", text("detected_at DESC")),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    log_source: Mapped[AuditSource] = mapped_column(
        String, nullable=False, default=AuditSource.agent
    )
    
    tool: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tool_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    http_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    auth_event: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_audit_org_ts", "org_id", text("ts DESC")),
        Index("idx_audit_tool", "org_id", "tool", text("ts DESC"), postgresql_where=text("tool IS NOT NULL")),
        Index("idx_audit_blocked", "org_id", text("ts DESC"), postgresql_where=text("allowed = false")),
        Index("idx_audit_auth", "org_id", "auth_event", text("ts DESC"), postgresql_where=text("auth_event IS NOT NULL")),
        Index("idx_audit_user", "org_id", "user_id", text("ts DESC"), postgresql_where=text("user_id IS NOT NULL")),
    )
