# Twin: Digital Doppelgänger

A web app that gives every user a personal AI twin. The twin learns from daily check-ins,
activity logs and chat, then predicts and recommends.

| Phase | Weeks | Status |
|---|---|---|
| 1. Foundation: auth, schema, onboarding, check-in, log | 1–2 | ✅ Done |
| 2. Learning inputs: chat + RAG memory, decisions, synthetic data, features | 3–4 | ✅ Done |
| 3. Core intelligence: patterns, predictions, SHAP, traits | 5–6 | ⏳ |
| 4. Adapt & ship: recommendations, what-if, privacy, deploy | 7–8 | ⏳ |

## Stack

- **frontend/**: Next.js 14 (App Router), TypeScript, Tailwind, shadcn-style UI, TanStack Query
- **backend/**: FastAPI, SQLAlchemy 2, Alembic, JWT (access + refresh), bcrypt, pandas
- **AI**: OpenAI (extraction + replies), sentence-transformers or OpenAI embeddings, pgvector memory
- **Database**: PostgreSQL 16 + pgvector (Docker for local development)

## Local setup

Prerequisites: Docker Desktop, Python 3.11+, Node 20+.

```bash
# 1. Database (Postgres + pgvector, on host port 5433)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -r requirements-local-embeddings.txt   # free local embeddings (large: PyTorch)
copy .env.example .env            # then set JWT_SECRET and OPENAI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
copy .env.example .env.local
npm run dev                       # http://localhost:3000  (Turbopack dev server)
```

> **Page speed.** In dev mode Next.js compiles each page the first time you open it.
> With Turbopack that takes about 0.2–0.5 s per page, and about 3 s for the very first one.
> Real users never see this delay. To try the app at production speed (about 10 ms per page,
> with pages prefetched), run `npm run preview`.
> If Turbopack ever misbehaves, `npm run dev:webpack` uses the classic compiler.

> The database uses port **5433**, not 5432, so it doesn't clash with a Postgres already
> installed on the machine.

### AI configuration (`backend/.env`)

| Setting | Values | Notes |
|---|---|---|
| `LLM_PROVIDER` | `openai` / `fake` | `fake` runs fully offline with simple deterministic replies |
| `OPENAI_CHAT_MODEL`, `OPENAI_EXTRACTION_MODEL` | default `gpt-4o-mini` | change without touching code |
| `EMBEDDING_PROVIDER` | `local` / `openai` / `fake` | all three use 384-dim vectors, so switching needs no migration |
| `CHAT_RATE_LIMIT_PER_MIN` | default 20 | protects your OpenAI budget |
| `DEMO_ENABLED` | `true` / `false` | enables `/demo/seed`; keep `false` in production |

With `EMBEDDING_PROVIDER=local`, the model (~90 MB) downloads once into `backend/.model_cache`.
It loads in the background when the server starts (`/health` shows `"embeddings": "loading"`).
Chat keeps working during the load. Messages sent meanwhile are embedded automatically once the
model is ready.

`python -m scripts.check_embeddings --provider local|openai` compares retrieval quality
(measured: local 8/10 top-1, OpenAI 9/10).

## Demo data

```bash
cd backend
python -m app.seed.synthetic_users            # 4 plan personas + 30 varied users, 90 days each
```

This creates logins such as `student@demo.example.com`, `developer@…`, `founder@…`, `noise@…`
and `user01.<role>@…` to `user30.<role>@…`, all with password `twin-demo-2026`.
Every user has hidden planted patterns (e.g. *under 6 h sleep → next-day focus −1.2*).
The ground truth is in `twin_profiles.onboarding.synthetic` and in `backend/data/ground_truth.json`.
Phase 3 must rediscover these patterns without being told.

You can also load one persona into your own account from **Settings → Demo data**.
This replaces your data, so the UI asks you to confirm first.

`backend/notebooks/feature_check.ipynb` shows the daily feature table for all demo users
and checks that the planted patterns are visible in it (the Phase 2 checkpoint).

## Tests

```bash
cd backend && pytest              # 84 tests against a real Postgres (twin_test DB), no API calls
ruff check . && ruff format --check .
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

The backend tests include:
- **Isolation**: user A cannot read, edit or delete user B's data, chat or decisions.
- **Migrations**: every migration runs down and up, and the models must match the migrations.
- **Auth hardening**: token types can't be swapped, tampered tokens are rejected, a race on
  registration returns 409, and login gives the same response for unknown emails and wrong passwords.
- **Chat**: nothing is saved before you confirm, edited values are what get saved, past
  messages are recalled, consent is respected, rate limits work, and LLM failures are handled.
- **Synthetic data**: each persona's planted patterns clear the plan's |ρ| ≥ 0.4 bar,
  averaged across seeds, and the noise control has no strong correlations.
- **Memory recall**: a user always gets their own memories, even next to hundreds of near-identical
  messages from other users. Recall uses an exact per-user search; an approximate HNSW search
  filtered by user returned 0 of 3 memories in this test.

Tests always use the fake LLM and fake embeddings, so they never need an API key.
CI (GitHub Actions) runs all of the above on every push and pull request.

## Known limitations (Phase 2)

- A task planned "for tomorrow" in chat is put on today's date in the card. Switch the card to the
  right day, or log it on the Log page.
- The chat page loads the latest 100 messages. Older history is kept and used for memory, but isn't
  shown yet.
- The chat rate limiter is in-memory, per server process (fine for one instance).
- Reply speed depends on OpenAI. Measured here: first word after about 3–5 s.

## Security and privacy notes

- The user id always comes from the JWT, never from the request body. Every query filters on it.
- Another user's rows return 404, not 403, so nobody can tell whether a row exists.
- When `APP_ENV=production`, the server refuses to start with a weak `JWT_SECRET` or a wildcard CORS origin.
- Secrets live in `.env` files, which git ignores. Only the `.env.example` templates are committed.
- The LLM receives only the current message, a few recent turns and retrieved snippets, never the
  whole history. No name or email is ever put in a prompt.
- If **Chat messages** consent is off, messages are still saved (so chat history works) but are
  never embedded, recalled or used for learning, even after the consent is switched back on.

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/refresh` | Tokens |
| GET | `/me` | User + twin profile |
| POST | `/onboarding` | Role, goals, categories, quiz (sets the starting trait estimates) |
| POST / GET | `/checkins` | Upsert today's check-in / list with `?from&to` |
| POST / GET | `/activities` | Create / list with `?from&to` |
| PATCH / DELETE | `/activities/{id}` | Tick off with actual minutes / remove |
| POST | `/chat` | Send a message. Streams NDJSON: `user_message`, `extraction`, `token`…, `done` |
| GET | `/chat/history` | Past messages with their confirmation cards |
| POST | `/chat/extractions/{id}/confirm` · `/dismiss` | Save the (edited) card / discard it |
| GET / POST | `/decisions` | List / add decisions |
| PATCH / DELETE | `/decisions/{id}` | Rate the outcome (1–5) / remove |
| GET / PUT | `/privacy/consents` | Per-source learning consent |
| POST | `/demo/seed` | Replace your data with a synthetic persona (when `DEMO_ENABLED=true`) |
| GET | `/health` | Liveness, database and embedding-model status |

Interactive docs: http://localhost:8000/docs
