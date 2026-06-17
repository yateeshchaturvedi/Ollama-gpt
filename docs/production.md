# Production Guide

This guide complements `docs/deployment.md` and focuses on production hardening, runtime safety, and recommended defaults.

## 1. Production Compose File

Use `docker-compose.prod.yml` for production:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

Why this file:
- Uses named volumes instead of host binds.
- Drops unnecessary container privileges where possible.
- Enables read-only filesystems for services that do not need writes.
- Adds tmpfs for `/tmp` and a dedicated log volume.

If a service fails to start due to filesystem writes, remove `read_only: true` for that service and add an explicit writable volume mount.

## 2. Pin Images (Do Not Use Mutable Tags)

Set explicit image versions in `.env.production`:

```
OLLAMA_IMAGE=ollama/ollama:<pin>
OPENWEBUI_IMAGE=ghcr.io/open-webui/open-webui:<pin>
AI_AGENT_IMAGE=ollama-gpt/ai-agent:<pin>
```

Pin versions that you have tested and approved. Avoid `latest` or `main` in production.

## 3. Secrets and Tokens

- Store secrets in an external secret manager (Azure Key Vault, AWS Secrets Manager, Vault, etc.).
- Do not store secrets in Git, Dockerfiles, or images.
- Rotate tokens regularly and after any incident.

## 4. Lock Down Tooling

Recommended production overrides (set in `.env.production`):

```
DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION=true
DANGEROUS_CONFIRMATION_TOKEN=<long-random-token>
ALLOWED_SHELL_PREFIXES=ls,dir,pwd,echo,cat,type
TOOL_RATE_LIMIT_COUNT=30
TOOL_RATE_LIMIT_WINDOW_SECONDS=60
```

## 5. Observability

- Persist tool audit logs via `TOOL_AUDIT_LOG_PATH`.
- Export container logs to your centralized logging stack.
- Add alerts for repeated tool denials or error spikes.

## 6. Resource Limits

Set service limits appropriate for your host and model:

- `ollama`: GPU/CPU limits and model cache volume size.
- `openwebui`: CPU/RAM caps.
- `ai-agent`: CPU/RAM caps and pids limits.

## 7. Backups

Back up:
- `ollama_data` volume (models cache)
- `openwebui_data` volume (user data)
- `agent_logs` volume (audit logs)

## 8. Incident Response

If you suspect misuse:

1. Rotate all service/API tokens.
2. Review tool audit logs.
3. Tighten `ALLOWED_SHELL_PREFIXES` and restrict workspace access.
4. Rebuild and redeploy with updated configuration.
