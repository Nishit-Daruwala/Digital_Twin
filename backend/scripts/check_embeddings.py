"""Does an embedding provider retrieve the right memory? (helps choose local vs OpenAI)

Run from backend/:
    python -m scripts.check_embeddings                 # local (sentence-transformers)
    python -m scripts.check_embeddings --provider openai
    python -m scripts.check_embeddings --provider fake # baseline: word overlap only

Each query has exactly one correct memory. Reports top-1 / top-3 hit rate and the
similarity margin between the right memory and the best wrong one.
"""

import argparse
import math
import time

MEMORIES = [
    "My exam on graph algorithms is next Friday and I'm nervous",
    "I always feel sluggish after big lunches with rice",
    "Had a fight with my roommate about the dishes again",
    "Started running 5k every morning before class",
    "My manager moved the product launch up by two weeks",
    "I can't fall asleep when I use my phone in bed",
    "Thinking about switching my major from physics to computer science",
    "Coffee after 4pm completely ruins my sleep",
    "Our team retro went really well, people liked my ideas",
    "I've been skipping breakfast and feel dizzy by noon",
    "My grandmother is visiting next weekend, need to clean the flat",
    "The client rejected the second design draft, very frustrating",
    "Meditating for ten minutes helped me calm down before the presentation",
    "I spent three hours on Instagram last night instead of studying",
]

QUERIES = [  # (query, index of the correct memory) -- paraphrased, few shared words
    ("How should I prepare for my algorithms test?", 0),
    ("Why am I so tired in the afternoon after eating?", 1),
    ("Things are tense with the person I live with", 2),
    ("Is my new jogging habit helping?", 3),
    ("Work deadline pressure got worse", 4),
    ("Tips for falling asleep faster?", 5),
    ("Should I change what I'm studying at university?", 6),
    ("Does caffeine affect my rest?", 7),
    ("What helps me with nerves before public speaking?", 12),
    ("I keep wasting evenings on social media", 13),
]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="local", choices=["local", "openai", "fake"])
    args = ap.parse_args()

    from app.core.config import settings

    settings.embedding_provider = args.provider
    from app.services.embeddings import embed

    t0 = time.perf_counter()
    mem = embed(MEMORIES)
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    qv = embed([q for q, _ in QUERIES])
    query_ms = (time.perf_counter() - t0) / len(QUERIES) * 1000

    top1 = top3 = 0
    margins = []
    for (q, right), v in zip(QUERIES, qv, strict=True):
        sims = sorted(((cos(v, m), i) for i, m in enumerate(mem)), reverse=True)
        ranked = [i for _, i in sims]
        top1 += ranked[0] == right
        top3 += right in ranked[:3]
        right_sim = next(s for s, i in sims if i == right)
        best_wrong = next(s for s, i in sims if i != right)
        margins.append(right_sim - best_wrong)
        mark = "ok " if ranked[0] == right else "MISS"
        print(f"  {mark} {q[:52]:<52} right={right_sim:.2f} best-wrong={best_wrong:.2f}")

    n = len(QUERIES)
    print(
        f"\nprovider={args.provider}  top-1 {top1}/{n}  top-3 {top3}/{n}  "
        f"mean margin {sum(margins) / n:+.3f}  first call {load_s:.1f}s  "
        f"per query {query_ms:.0f} ms"
    )


if __name__ == "__main__":
    main()
