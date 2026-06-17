# DevOps AI Hub

An intelligent, real-time DevOps CI/CD monitoring center and log diagnostics platform powered by **Google Gemini AI**. 

DevOps AI Hub automatically polls your configured repositories (GitHub, GitLab, Jenkins, Azure DevOps). The moment a build or pipeline fails, it downloads the failed log files, parses the stack traces, and streams a step-by-step root-cause diagnostic report directly to your dashboard in real-time.

---

## 🚀 Key Features

* **Multi-Platform CI/CD Support**: Unified monitoring for **GitHub Actions**, **GitLab Pipelines**, **Jenkins Job Builds**, and **Azure DevOps Pipelines**.
* **Real-time AI Diagnosis**: Direct WebSocket streaming of root-cause analyses and step-by-step fix recommendations from **Google Gemini 1.5 Pro**.
* **Polished Web Dashboard**: Next.js single-page center featuring real-time health indicator status, KPI statistics, platform breakdown badges, and relative timestamps.
* **Console Trace Log Viewer**: Read execution stdout logs in-browser, with log copy-to-clipboard, tail clear terminal console, and one-click manual AI diagnostic triggers.
* **Security & Tool Sandbox**: Strictly sandboxed local shell execution with command allowlists, tool call rate limiters, and mandatory manual confirmation token prompts.
* **Security Audit Logging**: Complete history of tool calls and sandbox permissions decisions, color-coded and tail-streamed via WebSocket.
* **Docker Compose Stack**: Single-command startup orchestrating Next.js, FastAPI, and volume state persistence.

---

## 🛠️ Architecture Overview

```
                        ┌─────────────────────────────────────────────────────────────┐
                        │                 Web Dashboard (Next.js)                     │
                        │  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌─────────────┐  │
                        │  │Dashboard │ │ GitHub   │ │ GitLab /  │ │  Log Viewer │  │
                        │  │Overview  │ │  Panel   │ │Jenkins/AZ │  │+ AI Analysis│  │
                        │  │(Alerts)  │ │  (Runs)  │ │ (Pipelines│  │(Audit Logs) │  │
                        │  └──────────┘ └──────────┘ └───────────┘ └─────────────┘  │
                        │       │              │              │              │         │
                        │  ─────┴──────────────┴──────────────┴──────────────┴──────  │
                        │                REST API + WebSocket (port 8000)              │
                        └──────────────────────────┬──────────────────────────────────┘
                                                   │
                        ┌──────────────────────────▼──────────────────────────────────┐
                        │              FastAPI Backend (agent/app/api/)                │
                        │  ┌─────────────────────────────────────────────────────┐    │
                        │  │              LLM Provider Layer                     │    │
                        │  │  BaseLLMClient → GeminiLLMClient (Active)            │    │
                        │  └─────────────────────────────────────────────────────┘    │
                        │  ┌─────────────────────────────────────────────────────┐    │
                        │  │              Dashboard monitor poller               │    │
                        │  │  Active background service polling repos.json       │    │
                        │  │  - On Failure: fetch log → stream Gemini analysis   │    │
                        │  └─────────────────────────────────────────────────────┘    │
                        └─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Quick Start

### 1. Prerequisites
Ensure you have the following installed on your machine:
* [Docker](https://www.docker.com/get-started) (v20.10+)
* [Docker Compose](https://docs.docker.com/compose/) (v2.0+)

### 2. Configure Environment
Clone the repository, copy the example environment file, and add your Google Gemini API key:

```bash
# Copy template file
cp .env.example .env
```

Open `.env` and configure your API details:
```env
# Google Gemini Settings
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-gemini-api-key-here
GOOGLE_MODEL=gemini-1.5-pro
```

### 3. Launch the Stack
Start the DevOps AI Hub services:

```bash
docker compose up --build -d
```

Once started, the services will be available at:
* **Web Dashboard**: [http://localhost:3000](http://localhost:3000)
* **FastAPI Backend (docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **System Health Endpoint**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 📋 Configuration Reference

| Environment Variable | Sensible Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | The active LLM client pattern (`gemini`, `openai`, `anthropic`). |
| `GOOGLE_API_KEY` | `""` | Google AI Platform credentials token. |
| `GOOGLE_MODEL` | `gemini-1.5-pro` | The Gemini model code identifier used for diagnosing build logs. |
| `MAX_TOOL_STEPS` | `5` | Safety threshold on recursive tool calls allowed per single request turn. |
| `MAX_HISTORY` | `12` | Turns history window count retained in memory buffer before trimming. |
| `DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION` | `true` | Prompt for manual `CONFIRM` token prior to execution of terminal commands. |
| `ALLOWED_SHELL_PREFIXES` | `ls,dir,pwd,echo,cat` | Command allowlist filter prefix tags for shell run tools. |

---

## 🧪 Testing & Verification

To run backend unit test suites locally, install requirements and execute:

```bash
cd agent
python -m pytest tests/ -q
```

*Expected output:*
```text
79 passed, 1 warning in 1.48s
```

To run frontend Next.js code quality compilation checks:
```bash
cd frontend
npm run build
```

---

## 🔒 Security Sandboxing Controls

The DevOps AI Hub includes security safeguards to protect your development environment:
1. **Workspace Isolation**: Read/write tools are strictly sandboxed to the local `./workspace` path. Attempts to traverse directories (e.g. `../../`) raise validation errors.
2. **Shell Prefix Filtering**: Executing shell commands runs through a strict allowlist matcher. Blocked commands reject instantly without triggering shells.
3. **Execution Audit**: Every tool call, status check outcome, and rejection is archived in `agent/logs/tool_audit.log` and tail-streamed to the UI audit dashboard.
