# Twin: Digital Doppelgänger

A web app that gives every user a personal AI twin. The twin learns from daily check-ins,
activity logs and chat, then predicts and recommends.

| Phase | Weeks | Status |
|---|---|---|
| 1. Foundation: auth, schema, onboarding, check-in, log | 1–2 | ✅ Done |
| 2. Learning inputs: chat + RAG memory, synthetic data, features | 3–4 | ⏳ |
| 3. Core intelligence: patterns, predictions, SHAP, traits | 5–6 | ⏳ |
| 4. Adapt & ship: recommendations, what-if, privacy, deploy | 7–8 | ⏳ |

## Stack

- **frontend/**: Next.js 14 (App Router), TypeScript, Tailwind, shadcn-style UI, TanStack Query
- **backend/**: FastAPI, SQLAlchemy 2, Alembic, JWT (access + refresh), bcrypt
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
copy .env.example .env            # then set JWT_SECRET (and OPENAI_API_KEY from Phase 2)
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
copy .env.example .env.local
npm run dev                       # http://localhost:3000
```

> The database uses port **5433**, not 5432, so it doesn't clash with a Postgres already
> installed on the machine.

## Tests

```bash
cd backend && pytest              # 33 API tests against a real Postgres (twin_test DB)
ruff check . && ruff format --check .
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

The backend tests include:
- **Isolation**: user A cannot read, edit or delete user B's data.
- **Migrations**: every migration runs down and up, and the models must match the migrations.
- **Auth hardening**: token types can't be swapped, tampered tokens are rejected, a race on
  registration returns 409, and login gives the same response for unknown emails and wrong passwords.

CI (GitHub Actions) runs all of the above on every push and pull request.

## Security notes

- The user id always comes from the JWT, never from the request body. Every query filters on it.
- Another user's rows return 404, not 403, so nobody can tell whether a row exists.
- When `APP_ENV=production`, the server refuses to start with a weak `JWT_SECRET` or a wildcard CORS origin.
- Secrets live in `.env` files, which git ignores. Only the `.env.example` templates are committed.

## API (Phase 1)

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/refresh` | Tokens |
| GET | `/me` | User + twin profile |
| POST | `/onboarding` | Role, goals, categories, quiz (sets the starting trait estimates) |
| POST / GET | `/checkins` | Upsert today's check-in / list with `?from&to` |
| POST / GET | `/activities` | Create / list with `?from&to` |
| PATCH / DELETE | `/activities/{id}` | Tick off with actual minutes / remove |
| GET / PUT | `/privacy/consents` | Per-source learning consent |
| GET | `/health` | Liveness + database check |

Interactive docs: http://localhost:8000/docs
