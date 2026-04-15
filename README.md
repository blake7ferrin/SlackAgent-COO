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

### Option A: `.env` file (local)

Copy `.env.example` to `.env` and fill values:

- `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- `XAI_API_KEY` (and optionally `XAI_BASE_URL`, `XAI_MODEL`)
- `BACKEND_BASE_URL`
- `BACKEND_GENERATE_REPORT_ENABLED` — set `true` to POST `generate_report` to the real backend (`false` uses mock-only for that tool)
- `GROK_REQUEST_TIMEOUT_SECONDS`, `BACKEND_HTTP_TIMEOUT_SECONDS`, `ORCHESTRATION_TIMEOUT_SECONDS`
- `LOG_LEVEL`

### Option B: [Doppler](https://www.doppler.com/) (recommended for teams / deploys)

This app only reads **environment variables** (via pydantic-settings). Doppler injects them at process start, so you do not need a `.env` file on the server.

1. Install the [Doppler CLI](https://docs.doppler.com/docs/install-cli) and run `doppler login` / `doppler setup` in the repo to link a project and config (for example `dev` or `prd`).
2. In the Doppler dashboard, add the same keys as in `.env.example` (use **uppercase** names: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `XAI_API_KEY`, etc.).
3. Run the app through Doppler:

```bash
doppler run -- uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Environment variables always override values from `.env` (pydantic-settings). To skip reading `.env` entirely (for example when only Doppler injects config), set `LOAD_DOTENV=0` in **Doppler or the shell** (not inside `.env` — that file is not read yet when this flag is applied).

Use the same keys as Option A in Doppler; you do not need a `.env` file on the machine if everything is in Doppler.

## Local run

On Debian/Ubuntu, install the venv module once if `python3 -m venv` fails (`ensurepip is not available`):

```bash
sudo apt-get update && sudo apt-get install -y python3.12-venv
```

Create a virtualenv, install dependencies, run uvicorn (Python **3.11+** is fine; this repo is tested on **3.12** in CI-like environments):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
# Edit .env with real Slack + xAI credentials before expecting Slack features to work.
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
