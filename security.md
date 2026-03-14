# Security Overview

This document explains security controls included in this project and what customers/operators must configure.

## Security Controls Included

### 1. Command Execution Restriction (Allowlist)

- `run_shell` is restricted by `ALLOWED_SHELL_PREFIXES`.
- Commands outside the allowlist are blocked.
- Location: `agent/app/tools/local_tools.py`, `agent/app/security.py`

### 2. File Access Sandbox

- `read_file` and `write_file` are restricted to `SAFE_WORKSPACE_ROOT`.
- Any file path outside the workspace root is blocked.
- Location: `agent/app/tools/local_tools.py`, `agent/app/security.py`

### 3. Dangerous Action Confirmation Gate

- `run_shell` and `write_file` require explicit confirmation token by default.
- `DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION=true`
- Expected arg field: `confirmation`
- Token value: `DANGEROUS_CONFIRMATION_TOKEN` (default `CONFIRM`)
- Location: `agent/app/tooling.py`, `agent/app/security.py`, `agent/app/protocol.py`

### 4. Tool Call Rate Limiting

- Tool invocations are rate-limited in-memory.
- Controls:
  - `TOOL_RATE_LIMIT_COUNT`
  - `TOOL_RATE_LIMIT_WINDOW_SECONDS`
- Location: `agent/app/security.py`, `agent/app/tooling.py`

### 5. Tool Audit Logging

- Tool usage is written as JSON lines with timestamps, tool names, allowed/denied status, and reason.
- Path controlled by `TOOL_AUDIT_LOG_PATH`.
- Location: `agent/app/security.py`, `agent/app/tooling.py`

### 6. Dependency Pinning

- Python dependencies are pinned in `agent/requirements.txt`.

### 7. CI Security Scanning

- GitHub Actions workflow runs:
  - `pip-audit` for dependency vulnerabilities
  - `bandit` for static Python security checks
- Location: `.github/workflows/security.yml`

## Secrets and Credential Safety

- Secrets are environment-driven (not hardcoded in compose files).
- `.env` is git-ignored.
- If secrets are exposed in logs/screenshots, rotate immediately.

Recommended secret stores:

- Azure Key Vault
- GitHub Actions Encrypted Secrets
- Docker/Orchestrator native secret stores

## Required Operator Configuration

Set these before production:

- `SAFE_WORKSPACE_ROOT`
- `ALLOWED_SHELL_PREFIXES`
- `DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION`
- `DANGEROUS_CONFIRMATION_TOKEN` (change from default)
- `TOOL_RATE_LIMIT_COUNT`
- `TOOL_RATE_LIMIT_WINDOW_SECONDS`
- `TOOL_AUDIT_LOG_PATH`

Also configure least-privilege tokens for:

- GitHub
- Slack
- Jenkins
- Azure DevOps
- GitLab

## Security Limitations

- Rate limiting is in-memory (non-distributed) and resets on container restart.
- LLM output still requires careful policy and monitoring.
- This project is not a full zero-trust execution sandbox.
- Additional controls recommended for enterprise use:
  - network egress restrictions
  - read-only container filesystem
  - non-root containers
  - SIEM integration
  - WAF/ingress auth controls

## Incident Response Checklist

If you suspect misuse:

1. Rotate all service/API tokens.
2. Review tool audit logs (`TOOL_AUDIT_LOG_PATH`).
3. Reduce allowlist and disable dangerous actions temporarily.
4. Review Slack channel/user access for bot commands.
5. Rebuild/redeploy with patched secrets and stricter policy.

