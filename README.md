# Twin: Digital Doppelgänger

A web app that gives every user a personal AI twin. The twin learns from daily check-ins,
activity logs and chat, then predicts and recommends.

| Phase | Weeks | Status |
|---|---|---|
| 1. Foundation: auth, schema, onboarding, check-in, log | 1–2 | ✅ Done |
| 2. Learning inputs: chat + RAG memory, decisions, synthetic data, features | 3–4 | ✅ Done |
| 3. Core intelligence: patterns, anomalies, predictions, SHAP, traits, accuracy | 5–6 | ✅ Done |
| 3.5 Time of day: check-in slots, daily rhythm, tomorrow by part of the day | — | ✅ Done |
| 4a. Adapt: recommendations, what-if, export/delete, adaptation + extraction evaluation, e2e | 7 | ✅ Done |
| 4b. Ship: deploy, polish, accessibility, final charts | 8 | ⏳ |

## Stack

- **frontend/**: Next.js 14 (App Router), TypeScript, Tailwind, shadcn-style UI, TanStack Query, Recharts
- **backend/**: FastAPI, SQLAlchemy 2, Alembic, JWT (access + refresh), bcrypt, APScheduler
- **ML**: pandas, SciPy, scikit-learn, XGBoost, SHAP (all per user, on that user's own data)
- **AI**: OpenAI (extraction + replies), sentence-transformers or OpenAI embeddings, pgvector memory
- **Database**: PostgreSQL 16 + pgvector (Docker for local development)

## Local setup

Prerequisites: Docker Desktop, Python 3.12+ (3.13 recommended; the ML libraries need ≥ 3.12), Node 22+.

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

## How the twin thinks (Phase 3)

A pipeline runs **nightly at 02:00**, on **Update now** (dashboard), and after demo seeding.
For each user with 3 or more days of data it runs: features → patterns → anomalies →
models + tomorrow's predictions + SHAP → resolve past predictions + accuracy → traits →
profile. Each run is logged in `job_runs`. A Postgres lock per user means runs never
overlap, and a failing step doesn't stop the others.

| Piece | How |
|---|---|
| **Patterns** (`ml/patterns.py`) | Spearman ρ for every feature/target pair at lag 0/1/2. Benjamini–Hochberg across all tests; keep \|ρ\| ≥ 0.4, adjusted p ≤ 0.05, n ≥ 10; rank by \|ρ\|·√n; median-split effect size. Leaky and trivial pairs are never tested. |
| **Insight wording** | The LLM rewords a fixed template. Code then checks that every number matches the evidence and that no causal claim was added; otherwise the template is kept. |
| **Anomalies** (`ml/anomaly.py`) | 14-day personal baseline, \|z\| ≥ 2 spikes, 3+ day streaks, plus an Isolation Forest for unusual combinations. |
| **Predictions** (`ml/predict.py`) | Tomorrow's mood and energy plus each planned task's completion chance. Inputs are *known tonight* or *plan-able* (tonight's sleep, tomorrow's plans, your typical day). Models learn the deviation from your 4-week norm. The ladder is average → Ridge/logistic → XGBoost, and a model is used only if it beats the norm by 5% over 21+ unseen days. |
| **SHAP** (`ml/explain.py`) | Top 3 reasons per prediction; reasons under 0.05 points are not shown. |
| **Traits** (`ml/traits.py`) | Chronotype, optimism bias, planner, consistency, stress triggers, best conditions. The quiz is used until 14 days of data; confidence grows with days. |
| **Accuracy** (`ml/accuracy.py`) | Hit = within 0.5 (or the right task outcome). Rolling 14-day hit rate, shown next to the 7-day-mean baseline's own hit rate. |

### Time of day (Phase 3.5)

A day has three **optional** check-in slots: **morning** (until 12:00), **afternoon**
(12:00–17:00) and **evening** (after 17:00; until 04:00 still counts as the evening before).
The first check-in of the day asks everything; later ones are quick (mood + energy). Any slot
can be skipped. Slots follow the user's timezone, which the browser sets on first load.

| Piece | How (`ml/intraday.py`) |
|---|---|
| **Daily rhythm** | Per slot, the usual offset, fitted as *value = day level + slot offset* by least squares **only on days with 2+ check-ins**. Comparing within the same day avoids the bias of "I only check in at night on bad days", and the two-way fit stays unbiased when days have different sets of slots. Offsets are shrunk toward 0 while evidence is thin (n / (n + 5)). |
| **Daily values** | Each check-in is adjusted for its slot, then the day's check-ins are averaged. Patterns, anomalies and the daily models learn from this, so a 9 AM and a 10 PM answer become comparable. |
| **Tomorrow by time of day** | The daily prediction plus the person's slot offset. Scored per slot against the check-in made in that slot; back-tested days use only the rhythm known the evening before. |
| **Rhythm statements** | "Your energy is usually higher in the morning than in the evening (3.6 vs 2.7, on 21 days you checked in at both)": a paired Wilcoxon test over 8+ days, Bonferroni-corrected, with a difference of at least 0.4 points. |

### Recommendations, what-if and privacy (Phase 4)

| Piece | How |
|---|---|
| **Recommendations** (`ml/recommend.py`) | Up to 3 a day, generated from the twin's own outputs: a lighter-day plan when tomorrow is predicted low, your best part of the day for hard work (time-of-day rhythm, else chronotype), padding time estimates (optimism bias), a check-in after an unusual stretch, acting on a discovered pattern (activities, sleep, start time; phrased as a pattern, not a cause), and stated goals that the last 7 days fall short of. Every reason quotes your own numbers. |
| **Learning from 👍 / 👎** | Score = relevance × preference. Default: discounted Thompson sampling, preference ~ Beta(2 + likes, 2 + dislikes) with each rating fading 5% a day. The plan's fixed weights (+0.1 / −0.15, clamped 0.2–2) are kept as `RECOMMEND_POLICY=weights`. One per type, a 👎 replaces the suggestion immediately and it doesn't return for 7 days. No medical or financial advice. |
| **What-if** (`ml/whatif.py`) | Same models and inputs as tomorrow's prediction (no changes = the dashboard's numbers). Only inputs a learned model uses become sliders, ranged to values you've actually had; if the twin predicts from your average alone it says so instead of showing sliders that do nothing. Shows the change, SHAP reasons and the time-of-day view; about 50 ms per change after the first. |
| **Privacy** | `GET /privacy/export` downloads everything as JSON (no password hash, no embeddings). `DELETE /me` needs your email typed, deletes every row (cascade) and the saved model files. |

### Evaluation (against planted ground truth)

```bash
cd backend
python -m app.ml.evaluate          # 34 users + 10 noise users, about 3 minutes
```

| Metric | Result | Plan target |
|---|---|---|
| Pattern recall@5 | 76% of 67 planted (75–82%, average 80%, over six random draws of check-in timing) | ≥ 80% |
| False insights per noise user | max 1, mean 0.09 | 0–1 |
| Twin MAE vs 7-day mean (14 → 60 days) | 3–7% better at every point | beats the baseline |
| Task completion AUC | ~0.6 | (reported) |
| Chronotype from data | ~70% correct | (reported) |
| Best energy slot learned (time of day) | 100% of 33 users | (reported) |
| Rhythm statements found and correct / false on noise users | 100% / 0 | (reported) |
| Predicting a check-in from the same day's others | 25% lower error with the rhythm | beats ignoring time of day |
| Adaptation: 👍 share of shown suggestions, week 1 → 4 (simulated users) | no learning 40% → 40%; plan weights 44% → 51%; Thompson 43% → 51% (ceiling ≈ 57%) | improves with feedback |
| Adaptation after tastes change (week 6) | no learning 41%; plan weights 46%; Thompson 46% | adapts |
| Extraction precision / recall on 50 labelled messages | offline regex stand-in: 96% / 58%; OpenAI: run after label review | (reported) |

`backend/notebooks/evaluation.ipynb` has the charts. A quick version runs in CI
(`tests/test_evaluation.py`) and fails the build if recall drops below 80%, a noise user gets
more than one insight, the twin stops beating the baseline, or the time-of-day rhythm is no
longer learned. The planted rhythms are clear by construction (energy moves up to 1 point
through the day), so real users will be noisier than these numbers.

Honest note on adaptation: Thompson sampling learns as well as the plan's fixed weights but
not better in these simulations (both reach most of the ≈57% ceiling; 2 liked types for 3
slots). It is the default because it explores untried advice in a principled way and, with
fading feedback, keeps up when tastes change.

Honest note on recall: before time of day, every synthetic user checked in once a day in the same
slot and recall was 84%. Now 15% of daily check-ins happen at an unusual time and some days add
quick check-ins, which is more realistic and noisier. Recall averages 80% across six random draws
of that timing (75–82%); the standard evaluation draw gives 76%. The time-of-day adjustment does
not change pattern recall on this data (80% with or without it); its benefit is the per-slot
forecasts, which are 25% more accurate.

The demo personas (`/demo/seed`, `python -m app.seed.synthetic_users`) are showcases: their
planted effects are scaled up (`strength` in `PERSONAS`) so the patterns are clearly visible after
60 days, and their seeds are chosen so the twin finds them whichever weekday the history ends on
(`tests/test_seed.py` checks every weekday). The numbers above use normal-strength users.

## Tests

```bash
cd backend && pytest              # 175 tests against a real Postgres (twin_test DB), no API calls
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

End-to-end (Playwright, `frontend/e2e/`): register → onboard → check-in → chat → dashboard →
what-if → export, and a demo twin where a 👎 replaces a suggestion, a what-if slider moves the
prediction and deleting the account works. Start both servers (backend with
`LLM_PROVIDER=fake`), then `cd frontend && npm run e2e` (add `PW_CHANNEL=msedge` to use the
installed Edge instead of downloading Chromium).

Extraction benchmark: `python -m app.ml.extraction_eval` runs the 50 labelled messages in
`backend/evals/extraction_cases.json` through the configured LLM (a few cents with OpenAI);
`--provider fake` runs the offline stand-in.

CI (GitHub Actions) runs lint, type checks, the backend tests, the quick evaluation and the
Playwright tests on every push and pull request.

## Known limitations

- A task planned "for tomorrow" in chat is put on today's date in the card. Switch the card to the
  right day, or log it on the Log page.
- The chat page loads the latest 100 messages. Older history is kept and used for memory, but isn't
  shown yet.
- The chat rate limiter is in-memory, per server process (fine for one instance).
- Task completion is hard to predict in advance (AUC ~0.6); the twin falls back to your personal completion rate unless a model is significantly better.
- Time-of-day forecasts need some days with 2+ check-ins; until then the dashboard only explains
  how to unlock them. Skipping a slot is remembered on that device only.
- Check-ins saved before Phase 3.5 have no reliable time of day and count as morning. This doesn't
  affect the learned rhythm, which only uses days with two or more check-ins.
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
| GET / PATCH | `/me` | User + twin profile / set the timezone |
| POST | `/onboarding` | Role, goals, categories, quiz (sets the starting trait estimates) |
| POST / GET | `/checkins` | Save a slot's check-in (full or quick; date and slot default to now) / list with `?from&to` |
| GET | `/checkins/today` | Today's three slots: which are done, started, current |
| POST / GET | `/activities` | Create / list with `?from&to` |
| PATCH / DELETE | `/activities/{id}` | Tick off with actual minutes / remove |
| POST | `/chat` | Send a message. Streams NDJSON: `user_message`, `extraction`, `token`…, `done` |
| GET | `/chat/history` | Past messages with their confirmation cards |
| POST | `/chat/extractions/{id}/confirm` · `/dismiss` | Save the (edited) card / discard it |
| GET / POST | `/decisions` | List / add decisions |
| PATCH / DELETE | `/decisions/{id}` | Rate the outcome (1–5) / remove |
| GET / PUT | `/privacy/consents` | Per-source learning consent |
| GET | `/privacy/export` | Download all your data as JSON |
| DELETE | `/me` | Delete the account and everything in it (`{"confirm_email": ...}`) |
| GET | `/recommendations` | Tomorrow's suggestions + what the twin learned from your thumbs |
| POST | `/recommendations/{id}/feedback` | `{"value": 1 \| -1 \| 0}`; a 👎 refills the list |
| GET / POST | `/whatif` | Sliders + baseline / predictions with `{"overrides": {...}}` |
| POST | `/demo/seed` | Replace your data with a synthetic persona (when `DEMO_ENABLED=true`) |
| GET | `/dashboard` | Accuracy, tomorrow's predictions, insights, traits, charts |
| GET | `/insights` | Active patterns and anomalies with their evidence |
| GET | `/predictions/tomorrow` · `/predictions/pending` | Predictions with SHAP reasons / ones to confirm |
| POST | `/predictions/{id}/confirm` | Real value (1–5, or 1/0 for tasks), updates accuracy |
| POST | `/jobs/retrain` · GET `/jobs/last` | Run the pipeline now / last run |
| GET | `/health` | Liveness, database and embedding-model status |

Interactive docs: http://localhost:8000/docs
