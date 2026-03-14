# Ollama GPT Agent

Local AI agent stack powered by Ollama, Open WebUI, and a Python tool-using agent.

## What This Project Does

- Runs Ollama locally for model inference.
- Exposes Open WebUI for browser-based chat.
- Runs a terminal-based agent that can:
  - call Ollama
  - execute shell commands
  - read files
  - write files
- Optional Slack bot integration via Socket Mode.
- Supports multi-turn conversation context and tool-calling loops.

## Architecture Overview

- `docker-compose.yml`: orchestrates three services:
  - `ollama`: model runtime
  - `openwebui`: browser UI
  - `ai-agent`: Python autonomous agent
  - `slack-agent` (optional profile): Slack Socket Mode bot worker
- `agent/agent.py`: terminal entrypoint (backward-compatible wrapper).
- `agent/slack_bot.py`: Slack worker entrypoint (backward-compatible wrapper).
- `agent/tools.py`: compatibility export for tools.
- `agent/app/`: production modules:
  - `app/config.py`: environment-driven settings
  - `app/clients/`: API clients (`ollama.py`)
  - `app/tools/`: local tools + GitHub tools
  - `app/protocol.py`: JSON tool-call protocol parsing
  - `app/tooling.py`: tool registry + validation/execution
  - `app/agent_runtime.py`: chat runtime loop
  - `app/slack_runtime.py`: Slack command/event runtime
- `agent/prompts/system_prompt.txt`: baseline system prompt loaded at runtime.

## Prerequisites

- Docker + Docker Compose
- Optional: Python 3.11+ (for running tests locally outside containers)

## Installation

1. Create your env file:

```bash
cp .env.example .env
```

2. Edit `.env` as needed (model name, retries, ports, optional `HF_TOKEN`).

3. Start the stack:

```bash
docker compose up --build
```

4. Pull a model in Ollama (example):

```bash
docker exec -it ollama ollama pull llama3
```

## Usage

### Open WebUI

- Open `http://localhost:3000` (or your configured `OPENWEBUI_PORT`).

### Interactive Agent

```bash
docker exec -it ai-agent python agent.py
```

Type prompts and use `exit` or `quit` to stop.

### One-shot Prompt

```bash
docker exec -it ai-agent python agent.py --prompt "List files in current directory"
```

### Prompt From File

```bash
docker exec -it ai-agent python agent.py --prompt-file prompts/request.txt
```

### Slack Integration (Optional)

1. Create a Slack app and enable Socket Mode.
2. Add bot scopes:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `im:history`
3. Install the app to your workspace.
4. Set values in `.env`:
   - `SLACK_BOT_TOKEN=xoxb-...`
   - `SLACK_APP_TOKEN=xapp-...`
   - `SLACK_ALLOWED_CHANNEL=` (optional channel ID restriction)
   - `SLACK_REQUIRE_MENTION=true` (set `false` to reply to all messages in allowed channel/DM)
5. Start slack worker profile:

```bash
docker compose --profile slack up -d --build slack-agent
```

The bot responds in DMs, and in channels when it is mentioned.
Model selection commands in Slack:
- `/models` -> list available models from Ollama
- `/model` -> show current model for that thread/channel
- `/model <model_name>` -> set model for that thread/channel
- `/model reset` -> revert to default `OLLAMA_MODEL`
GitHub integration prompts (examples):
- `@ai_channel check latest workflow runs for repo owner/repo`
- `@ai_channel show run logs summary for run 123 in owner/repo`
- `@ai_channel review PR 42 in owner/repo`
Direct GitHub command mode in Slack:
- `/gh help`
- `/gh runs owner/repo`
- `/gh run owner/repo 123456789`
- `/gh retry owner/repo 123456789`
- `/gh cancel owner/repo 123456789`
- `/gh pr overview owner/repo 42`
- `/gh pr files owner/repo 42 20`
- `/gh pr review owner/repo 42 20`
- `/gh pr comment owner/repo 42 LGTM after addressing comments`
- `/gh checks owner/repo 42`
- `/gh deploy owner/repo`
- `/gh issues owner/repo`
- `/gh security owner/repo`
- `/gh changelog owner/repo v1.2.0 main`
- `/gh release-note owner/repo 42 v1.2.0 main`
- `/gh dashboard owner/repo,owner/repo2`
- `/gh digest owner/repo,owner/repo2`

Background automations:
- Auto-failure alerts for GitHub Actions to a Slack channel.
- Scheduled daily digest for CI/PR/security health.

## Configuration

Configure via `.env` (consumed by Docker Compose and the agent):

- `OLLAMA_PORT` (default: `11434`)
- `OPENWEBUI_PORT` (default: `3000`)
- `OLLAMA_MODEL` (default: `llama3`)
- `OLLAMA_TIMEOUT_SECONDS` (default: `60`)
- `OLLAMA_RETRIES` (default: `3`)
- `MAX_TOOL_STEPS` (default: `5`)
- `MAX_HISTORY` (default: `12`)
- `LOG_LEVEL` (default: `INFO`)
- `HF_TOKEN` (optional, no hardcoded secrets)
- `GITHUB_TOKEN` (optional, required for GitHub Actions/PR tools)
- `GITHUB_API_URL` (default: `https://api.github.com`)
- `GITHUB_MONITOR_REPOS` (comma-separated repos for failure alert polling)
- `GITHUB_ALERT_CHANNEL` (Slack channel ID for failure alerts)
- `GITHUB_ALERT_POLL_SECONDS` (default: `120`)
- `GITHUB_DIGEST_REPOS` (comma-separated repos for digest)
- `GITHUB_DIGEST_CHANNEL` (Slack channel ID for digest)
- `GITHUB_DIGEST_HOUR` (default: `9`)
- `GITHUB_DIGEST_MINUTE` (default: `0`)
- `GITHUB_TZ_OFFSET_MINUTES` (default: `330`, IST)
- `SLACK_BOT_TOKEN` (optional, required for Slack profile)
- `SLACK_APP_TOKEN` (optional, required for Slack profile)
- `SLACK_ALLOWED_CHANNEL` (optional channel ID limit for bot messages)
- `SLACK_REQUIRE_MENTION` (default: `true`, require `@mention` in channels)
- `MAX_SLACK_REPLY_CHARS` (default: `38000`)

## Testing and Validation

Run tests:

```bash
cd agent
python -m pytest -q
```

Validate Compose config:

```bash
docker compose config
```

Validate Ollama connectivity:

```bash
docker exec -it ai-agent python -c "import requests; print(requests.get('http://ollama:11434').status_code)"
```

## Troubleshooting

- Agent cannot reach Ollama:
  - Verify `ollama` container is healthy: `docker compose ps`
  - Check `OLLAMA_HOST` is `http://ollama:11434` in container context.
- Model not found:
  - Pull it manually inside Ollama container: `docker exec -it ollama ollama pull <model>`.
- Tool calls not executing as expected:
  - Increase logging: set `LOG_LEVEL=DEBUG`.
  - Check agent output for JSON tool-call shape.
- Compose startup issues:
  - Run `docker compose logs -f` and inspect failing service logs.

## Security Notes

- No tokens are hardcoded in Compose.
- Keep `.env` out of version control (`.gitignore` includes it).
- Limit shell tool usage if running in shared or untrusted environments.
