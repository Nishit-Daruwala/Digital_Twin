# Demo script (5 minutes)

The plan's demo, step by step, with what to click and what to say. Rehearse it once with
the exact accounts below; every number quoted on screen comes from the twin, not from this
script.

## Before the demo

```bash
docker compose up -d                                   # Postgres + pgvector
cd backend && python -m app.seed.synthetic_users       # demo accounts, 90 days each (once)
uvicorn app.main:app --port 8000                       # API (real OpenAI for chat)
cd frontend && npm run build && npm start              # production build: pages open instantly
```

- Accounts: `student@demo.example.com` and `developer@demo.example.com`, password
  `twin-demo-2026`.
- Open both accounts once before the demo, so the twin has already trained (the
  dashboard shows insights, not "learning").
- Use a production build (`npm start`), not `npm run dev`. The dev server compiles each page
  the first time it opens, which looks slow on camera.
- Browser at 100% zoom, 1366×900 or larger. Close other tabs.

## The five minutes

| Time | Do | Say |
|---|---|---|
| 0:00 | Log in as **student**. Dashboard. | "This is a twin of one person, built only from their own check-ins, logs and chat. No generic advice." |
| 0:20 | Point at the insight cards, the personality card and the accuracy ring. | "It found these patterns itself. Each one passed a significance test with a correction for testing many at once." |
| 0:45 | Click **Why?** on the sleep insight. | "The evidence: Spearman ρ, how many days, and the size of the effect. The sentence is generated, but its numbers are checked against this evidence." |
| 1:10 | **Chat**: type *"Why am I always tired on Wednesdays?"* | "It answers from this user's own data and past messages, retrieved from a vector index, never from other users." |
| 1:50 | **What-if**: move *Sleep tonight* to 7 h. | "Same models as tomorrow's prediction. The number moves, and the bars show why (SHAP). Sliders only go as far as values this person has actually had." |
| 2:40 | Dashboard → **Suggestions for tomorrow**: 👎 one, open *What your twin has learned*. | "A thumbs-down replaces it at once, and that kind of advice becomes less likely. Over four weeks, feedback raises accepted suggestions from about 44% to 51% in our simulation." |
| 3:20 | Log out, log in as **developer**. Dashboard. | "Same code, a different person, a different twin: morning peak, meetings drain energy, Mondays are low." |
| 4:00 | **Settings → Your data**: *Download my data*, then show the delete box. | "Everything is exportable as JSON. Delete needs the email typed and removes every row and the saved models. Consents switch off whole data sources." |
| 4:30 | Close on the evaluation chart (`docs/figures/learning_curve.png`). | "On synthetic users with planted patterns, it finds about 80% of them and invents at most one on pure noise." |

## If something goes wrong

- **Chat is slow or fails:** OpenAI is down or out of quota. Say so, and show the
  extraction card with a check-in message instead (works the same with the fake provider).
- **Dashboard says "learning":** the account has not been trained yet. Settings → Demo data →
  load the persona (60 days), wait about 30 s.
- **429 "Too many…":** a rate limit. Wait the seconds shown; it protects the login and
  the OpenAI budget.

## Recording the video

- 1080p, browser only (hide bookmarks), system notifications off.
- Record each row as its own clip, then cut. Retakes are cheaper than a perfect single take.
- Captions: the "Say" column above.
