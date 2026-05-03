# Shopify CSM Agent

An autonomous customer-success agent that triages incoming Shopify customer
messages, looks up the relevant order context via the Shopify Admin API,
drafts a reply with an LLM, and either posts a draft to Slack for human
approval or replies directly when the message is unambiguous and low-risk.

Built to be deployable on a small VPS (Hostinger / GCP / DigitalOcean) behind
Tailscale, run as a systemd service or a Docker container, and operated
autonomously across multiple client stores from a single deployment.

---

## What it does

```
   Customer message  ─┐
                      │
     Shopify webhook ─┤
       /              │
      /               ▼
 ┌──────────────────────────┐
 │  FastAPI ingest endpoint │
 └──────────┬───────────────┘
            │
            ▼
 ┌──────────────────────────┐    ┌──────────────────────┐
 │   Agent loop (LangGraph) │◄──►│  Tools               │
 │   - classify intent      │    │  - shopify.orders    │
 │   - gather context       │    │  - shopify.products  │
 │   - draft reply          │    │  - shopify.customers │
 │   - confidence check     │    │  - kb.search         │
 │   - act / escalate       │    │  - slack.post        │
 └──────────┬───────────────┘    └──────────────────────┘
            │
            ▼
   ┌─────────────────┐    ┌──────────────────┐
   │ Auto-reply path │    │ Human-in-loop    │
   │ (high conf.)    │    │ Slack approval   │
   └─────────────────┘    └──────────────────┘
```

**Supported intents (out of the box):**

- Order status / tracking
- Refund / return requests
- Product availability and variants
- Shipping address change
- Discount / coupon enquiry
- General product questions (RAG over the store's FAQ)

Anything outside this set, or anything where confidence is low, is escalated
to Slack with the full context and a draft reply for an operator to approve,
edit, or reject.

---

## Stack

| Concern              | Choice                             |
| -------------------- | ---------------------------------- |
| Agent runtime        | LangGraph + LangChain (Python 3.11)|
| LLM                  | Anthropic Claude (Sonnet) — pluggable provider |
| Web framework        | FastAPI + Uvicorn                  |
| Job queue            | Redis + RQ                         |
| Storage              | SQLite (dev) / Postgres (prod)     |
| Observability        | structlog + OpenTelemetry          |
| Deployment           | Docker Compose / systemd           |
| Network              | Tailscale (admin), Caddy (public)  |

The LLM provider is abstracted behind a thin interface so it can be swapped
between Anthropic, OpenAI, or a self-hosted model.

---

## Repo layout

```
shopify-csm-agent/
├── src/
│   ├── agent/
│   │   ├── graph.py           # LangGraph state machine + node functions
│   │   ├── llm.py             # provider-agnostic LLM adapter
│   │   └── prompts.py         # system prompts for classify, draft, self-grade
│   ├── tools/
│   │   ├── shopify.py         # Admin API wrapper (httpx + retry/back-off)
│   │   └── slack.py           # Block Kit review-card poster
│   ├── api/
│   │   ├── main.py            # FastAPI app + lifespan-managed graph deps
│   │   └── webhooks.py        # Shopify webhook handler with HMAC verify
│   └── settings.py            # pydantic settings
├── tests/
│   └── test_agent_graph.py    # unit tests for the decision branches
├── deploy/
│   ├── docker-compose.yml     # api / worker / redis / caddy
│   ├── Dockerfile
│   └── Caddyfile
├── docs/
│   ├── runbook.md             # VPS deploy and ops
│   └── client_onboarding.md   # per-client setup checklist
├── .env.example
├── pyproject.toml
├── push.sh
└── README.md
```

---

## Quick start (local)

```bash
git clone git@github.com:KaimuMutz/shopify-csm-agent.git
cd shopify-csm-agent

cp .env.example .env
# Fill in: SHOPIFY_STORE, SHOPIFY_ADMIN_TOKEN, ANTHROPIC_API_KEY,
# SLACK_BOT_TOKEN, SLACK_REVIEW_CHANNEL

python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Run the API + worker locally
uvicorn src.api.main:app --reload --port 8000
```

Send a sample customer message:

```bash
curl -X POST http://localhost:8000/v1/messages \
     -H "Content-Type: application/json" \
     -d '{"customer_email":"sam@example.com","body":"Where is order #1042?"}'
```

You should see (a) a classified intent, (b) an order-status lookup, and
(c) either an auto-reply or a draft posted to your Slack review channel.

---

## Deploying to a VPS

The full runbook lives in `docs/runbook.md`. The short version:

1. Provision a small VPS (1 vCPU / 2 GB is enough for ~10 stores).
2. `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up`
   to bring it onto the private mesh.
3. `docker compose -f deploy/docker-compose.yml up -d`
4. Point your Shopify webhook to `https://csm.<client>.your-domain/webhooks/shopify`
   (Caddy handles TLS automatically).
5. In Slack, configure the bot's **Interactive Components** request URL
   to point at `https://csm.<your-domain>/slack/callback` so Approve /
   Edit / Reject button clicks land back at the agent (handler is on
   the roadmap; buttons render today).

Each client store gets its own row in the `clients` table — credentials,
Slack channel, auto-reply confidence threshold, and tone of voice are all
per-client. One deployment, many stores.

---

## Operating model

- **Confidence gate.** Every drafted reply carries a confidence score
  (0–1) derived from intent classification + tool-call success + a
  self-grading pass. Replies below the per-client threshold are always
  escalated.
- **Risk gate.** Refunds, address changes, and any reply mentioning a
  monetary value are escalated regardless of confidence.
- **Audit trail.** Every conversation gets a UUID; the conversation ID is
  returned in the HTTP response and emitted with every structured log line,
  so a customer-reported issue triages back to a specific run. A database-
  backed `Conversation` model is defined; full persistence and an
  `/admin/conversations/<id>` debug endpoint are on the roadmap.
- **Cost controls.** Per-client `DAILY_TOKEN_BUDGET_USD` lives in the
  client config. Runtime token accumulation and auto-escalation on budget
  overrun are on the roadmap.

---

## Status

Active development. Validated end-to-end locally against a Shopify
development store with real Slack and Anthropic API calls. Production
deployment runbook in `docs/runbook.md`; per-client setup steps in
`docs/client_onboarding.md`.

---

## License

MIT.
