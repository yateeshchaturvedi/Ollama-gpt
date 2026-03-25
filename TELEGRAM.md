# Telegram Bot Integration

This project supports Telegram bot integration alongside the existing Slack integration. The Telegram bot provides full AI agent capabilities with multi-turn conversations, model selection, and GitHub integration.

## Setup Guide

### 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the instructions to create a new bot
3. Choose a name for your bot (e.g., "My AI Agent")
4. Choose a username for your bot (e.g., "my_ai_bot")
5. You'll receive a token that looks like: `123456789:ABCdefGHIjklmnoPQRstuvwxyzABCDEFGhij`
6. Save this token as your `TELEGRAM_BOT_TOKEN`

### 2. Configure Environment Variables

Add the following to your `.env` file:

```bash
# Required
TELEGRAM_BOT_TOKEN=<your_bot_token_from_botfather>

# Optional: Restrict access to specific user IDs (comma-separated)
# Leave empty to allow all users
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Optional: Maximum message length (Telegram limit is 4096)
MAX_TELEGRAM_REPLY_CHARS=4096

# Optional: For GitHub alerts and digests
GITHUB_ALERT_CHAT_ID=<your_chat_id>        # For failure alerts
GITHUB_DIGEST_CHAT_ID=<your_chat_id>       # For daily digest
```

#### Getting Your Chat ID

To find your chat ID:

1. Start your Telegram bot (see step 3)
2. Send any message to the bot
3. Check the logs: `docker logs telegram-agent | grep "chat_id"`
4. Look for a line like: `INFO Incoming Telegram message from user_id=123456789 chat_id=987654321`
5. Use the `chat_id` value in your environment variables

### 3. Start the Telegram Bot

Run the Telegram bot worker:

```bash
docker compose --profile telegram up -d --build telegram-agent
```

To see logs:

```bash
docker logs -f telegram-agent
```

To stop the bot:

```bash
docker compose --profile telegram down
```

## Usage

### Chat Commands

Send messages to your bot on Telegram:

- **`/start`** → Show help and available commands
- **`/models`** → List all available Ollama models
- **`/model`** → Show current model for this conversation
- **`/model <model_name>`** → Switch to a specific model for this conversation
- **`/model reset`** → Reset to default model
- **Any other message** → Chat with the AI agent

### GitHub Commands

Use GitHub commands with `/gh`:

```
/gh help                              # Show all GitHub commands
/gh runs owner/repo                   # List recent workflow runs
/gh run owner/repo <run_id>          # Show specific run logs
/gh retry owner/repo <run_id>        # Retry a failed workflow
/gh cancel owner/repo <run_id>       # Cancel a running workflow
/gh pr overview owner/repo <pr_num>  # PR summary
/gh pr files owner/repo <pr_num>     # Changed files in PR
/gh pr review owner/repo <pr_num>    # Review suggestions
/gh pr comment owner/repo <pr_num> <comment_text>  # Post comment on PR
/gh checks owner/repo <pr_num>       # Check required status checks
/gh deploy owner/repo                # Deployment status
/gh issues owner/repo                # Recent issues
/gh security owner/repo              # Security summary
/gh changelog owner/repo <base> <head>  # Changelog between refs
/gh dashboard owner/repo1,owner/repo2   # Multi-repo dashboard
/gh digest owner/repo1,owner/repo2      # Daily digest
```

### Example Conversation

```
User: /models
Bot: Available models:
     - llama3
     - mistral
     - neural-chat

User: /model mistral
Bot: Model set to `mistral` for this chat.

User: Write a Python function to validate email addresses
Bot: [AI generates Python code]

User: Can you explain this code?
Bot: [AI explains the code with context from previous messages]

User: /gh pr overview myorg/myrepo 42
Bot: [Shows PR details from GitHub]
```

## Advanced Configuration

### Restricting Access

To only allow specific users to use the bot, set their Telegram user IDs:

```bash
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

To find your user ID:
1. Start the bot
2. Send any message
3. Check logs for your `user_id`

### GitHub Alerts and Digests

Configure automatic GitHub notifications:

```bash
# Monitor these repos for workflow failures
GITHUB_MONITOR_REPOS=owner/repo1,owner/repo2

# Send alerts to this chat
GITHUB_ALERT_CHAT_ID=<your_chat_id>

# Send daily digests to this chat
GITHUB_DIGEST_REPOS=owner/repo1,owner/repo2
GITHUB_DIGEST_CHAT_ID=<your_chat_id>

# Digest time settings (9:00 AM IST by default)
GITHUB_DIGEST_HOUR=9
GITHUB_DIGEST_MINUTE=0
GITHUB_TZ_OFFSET_MINUTES=330  # IST is UTC+5:30 (330 minutes)
```

For other timezones:
- **EST**: `-300`
- **CST**: `-360`
- **MST**: `-420`
- **PST**: `-480`
- **UTC**: `0`
- **GMT+1**: `60`
- **IST (UTC+5:30)**: `330`
- **JST (UTC+9)**: `540`
- **AEST (UTC+10)**: `600`

### Shared Features with Slack

The Telegram bot shares the same GitHub and Jenkins integration capabilities as the Slack bot:

- **Jenkins integration**: Set `JENKINS_URL`, `JENKINS_USER`, `JENKINS_API_TOKEN`
- **Azure DevOps**: Set `AZDO_ORG_URL`, `AZDO_PAT`
- **GitLab**: Set `GITLAB_URL`, `GITLAB_TOKEN`

## Troubleshooting

### Bot not responding

1. Check the bot token:
   ```bash
   docker logs telegram-agent | grep "TELEGRAM_BOT_TOKEN"
   ```

2. Verify the bot token is correct from BotFather

3. Check logs for errors:
   ```bash
   docker logs telegram-agent | tail -20
   ```

### "You are not authorized" error

- Check your user ID is in `TELEGRAM_ALLOWED_USER_IDS`
- If the list is empty, all users are allowed
- Restart the bot: `docker compose --profile telegram restart telegram-agent`

### Messages not being processed

1. Ensure Ollama is running and healthy:
   ```bash
   docker logs ollama
   ```

2. Check the Ollama host is correctly set:
   ```bash
   echo $OLLAMA_HOST
   ```

3. Verify there's space in the conversation history:
   ```bash
   docker logs telegram-agent | grep "Thinking\|Processing"
   ```

### Rate limiting or timeouts

Increase the timeout:

```bash
OLLAMA_TIMEOUT_SECONDS=120
```

### Model not switching

Use the exact model name from `/models`:

```
/model llama3         # ✅ Correct
/model Llama 3        # ❌ Wrong
/model llama3:latest  # ✅ Also works
```

## Running Both Slack and Telegram

You can run both bots simultaneously:

```bash
# Start both
docker compose --profile slack --profile telegram up -d --build

# Or start separately
docker compose --profile slack up -d --build slack-agent
docker compose --profile telegram up -d --build telegram-agent
```

## Architecture

The Telegram integration (`app/telegram_runtime.py`) mirrors the Slack implementation:

- **Polling**: Uses long-polling to receive messages (simple, no webhook needed)
- **Conversation History**: Per-chat conversation tracking
- **Model Selection**: Per-chat model selection independent of other chats
- **Tool Integration**: Full access to GitHub, Jenkins, Azure DevOps, and GitLab tools
- **Background Workers**: Failure alert polling and daily digest scheduling

## Differences from Slack

| Feature | Slack | Telegram |
|---------|-------|----------|
| Connection | Socket Mode | Long Polling |
| Webhook | Required | Not required |
| Message Threads | Native support | Replies to message_id |
| User Auth | Team-based | User ID list |
| Channel Restriction | By channel ID | By chat ID |
| Max Message | 38000 chars | 4096 chars (Telegram limit) |

## Support

For issues or feature requests, check the main README and project documentation.
