# Home service Slack orchestrator (Grok + existing backend)

This repository is a **Slack agent / orchestration layer** for an HVAC / plumbing / electrical operations workflow.

It is intentionally **not** a report engine. Your existing backend remains the source of truth for schemas, validation, templates, PDF generation, and downstream business logic. This service:

- receives Slack events (mentions, thread messages, DMs, file uploads)
- builds structured thread context (including HTTPS image URLs from Slack file metadata)
- calls **xAI Grok** with tool definitions
- executes tools that **HTTP call your backend** (with safe mocks if the backend is down)
- replies in the correct Slack thread

## Project layout

```
app/
  api/            FastAPI routes (health + Slack mount)
  slack/          Bolt app, dedupe, normalization, event pipeline
  grok/           Grok client + orchestration loop + system prompt file
  tools/          Pydantic tool I/O + mappers + dispatcher + backend HTTP client + mocks
  models/         Shared pydantic models
  services/       Thread context builder + Slack reply helper
  config/         Settings
  utils/          Logging helpers
main.py           FastAPI entrypoint + uvicorn hook
```

## Configuration

Copy `.env.example` to `.env` and fill values:

- `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- `XAI_API_KEY` (and optionally `XAI_BASE_URL`, `XAI_MODEL`)
- `BACKEND_BASE_URL`
- `BACKEND_GENERATE_REPORT_ENABLED` — set `true` to POST `generate_report` to the real backend (`false` uses mock-only for that tool)
- `GROK_REQUEST_TIMEOUT_SECONDS`, `BACKEND_HTTP_TIMEOUT_SECONDS`, `ORCHESTRATION_TIMEOUT_SECONDS`
- `LOG_LEVEL`

## Local run

Create a virtualenv, install dependencies, run uvicorn:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expose `/slack/events` to the internet (ngrok/Cloudflare Tunnel/etc.) and configure Slack:

- **Event Subscriptions** → Request URL: `https://<public-host>/slack/events`
- Subscribe to bot events: `app_mention`, `message.channels` (and/or `message.groups`), `message.im`, `file_shared`
- **OAuth scopes** (typical): `app_mentions:read`, `channels:history`, `channels:read`, `chat:write`, `files:read`, `groups:history`, `groups:read`, `im:history`, `im:read`, `users:read`

## Behavior notes

- **Bot loop protection**: ignores `bot_message` / `bot_id` messages and ignores messages sent by this bot user.
- **Deduping**: in-memory TTL dedupe for Slack retries (`event_id`, message keys, file ids).
- **Channel noise control**: in `C…`/`G…` channels, the bot reacts to **thread replies** (threaded messages) or explicit `<@BOT>` mentions. DMs (`D…`) are handled for all messages.
- **Images**: only **HTTPS** URLs are included; for Slack uploads, `url_private` is used when `mimetype` starts with `image/`.
- **Report workflow pre-check**: before Grok runs, the thread must have usable notes and/or HTTPS images; images-only threads get a short context question.
- **Slack reply modes**: *Missing information*, *Processing* (in-thread ping before Grok), then *Completed* / *Failed* on the final message.

## Replace mocks / wire real backend endpoints

Edit `app/tools/implementations.py`:

- For **`generate_report`**: set `BACKEND_GENERATE_REPORT_ENABLED=true`, then adjust `POST /v1/reports` path and JSON body to match your backend. On HTTP/network failure the tool returns **`ok: false`** (no silent mock fallback).
- Other tools still use HTTP with mock fallbacks when the backend is unreachable.

## Grok system prompt

`app/grok/prompts/system_prompt.txt` is loaded at runtime (easy to iterate without code changes).
