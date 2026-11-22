# tech-digest

A Mistral Workflow that reads the Hacker News front page, keeps only tech-industry
stories, and emails a digest with a short podcast-style audio briefing attached.

## What it does

1. `fetch_hn_front_page` — reads the top stories from the public HN Firebase API.
2. `curate_tech_stories` — an LLM keeps only tech-industry news (companies, products,
   startups, funding, AI, semiconductors, developer tools, cybersecurity, tech policy)
   and drops personal blogs, essays, and other topics.
3. `write_podcast_script` — an LLM writes a spoken script under 300 words (~2 minutes).
4. `synthesize_podcast_audio` — Voxtral TTS (`voxtral-mini-tts-3-0`) renders the script
   to MP3.
5. `send_digest_email` — sends the digest via the workspace `gmail` connector, with the
   audio attached (skipped if it exceeds Gmail's attachment limit).

The workflow runs `on_behalf_of` the triggering user, so the email is sent from their
authenticated Gmail account. There is no schedule: it is a one-shot task, started on
demand (from Mistral Studio or `execute_workflow`).

## Run it yourself (self-hosted worker)

Run the worker on your own machine; it registers with Mistral's hosted control plane, so you
can trigger runs on demand from Mistral Studio — no managed deployment slot needed.

1. Install the Mistral CLI and sign in:
   ```bash
   curl -fsSL https://mistral.ai/cli/install.sh | bash
   mistral login
   ```
2. Clone this repo and configure the worker:
   ```bash
   git clone https://github.com/3rdbrain/tech-digest && cd tech-digest
   cp .env.example .env
   # put a Mistral API key (console.mistral.ai → API keys) into MISTRAL_API_KEY in .env
   ```
3. Serve the worker:
   ```bash
   bun install          # installs the pinned toolchain (bun is required only here)
   mistral apps dev --filter worker
   ```
   (No bun? `bash tools/uv.sh sync --all-packages` then `bash tools/uv.sh run --all-packages python -m worker.entrypoints.dev` works too.)
4. Trigger: in Mistral Studio → Workflows → `hn-tech-digest` → Run with input `{}`.
   Approve the Gmail OAuth prompt when asked — the email is sent from your account.

The first `curl` step needs an API key with available usage; when your plan's included
monthly usage is exhausted, enabling pay-as-you-go with credits in the console is required.

## Layout

- `apps/worker/src/worker/workflows/tech_digest.py` — the workflow and activities.
- `apps/worker/tests/` — discovery and rendering tests.
- `.agents/skills/capability-workflows/` — vendored Workflows SDK skill and references.

## Local checks

```bash
bun install
bunx nx run worker:semgrep
cd apps/worker && bash ../../tools/uv.sh run --all-packages python -m pytest tests/ -q
```

## Deployment

Deployed as a managed workflow deployment on Mistral Cloud; the worker serves the
`hn-tech-digest` workflow. Trigger it with input `{}` (defaults: recipient from the
code default, 10 front-page stories) or `{"recipient": "you@example.com"}`.
