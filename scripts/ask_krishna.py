"""
Answer questions as Lord Krishna using RAG — same pipeline you learned:

rewrite query -> retrieve -> rerank -> answer

Run:
    python scripts/ask_krishna.py "I am anxious about my future. What should I do?"
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import retry, wait_exponential

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local", override=True)

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "data" / "gita-index.json"

MODEL = os.getenv("KRISHNA_MODEL", "gpt-4o-mini")
embedding_model = "text-embedding-3-small"
RETRIEVAL_K = 20
FINAL_K = 8
wait = wait_exponential(multiplier=1, min=4, max=60)

SYSTEM_PROMPT = """
You are Lord Krishna — the same beloved friend who stood as Arjuna's charioteer
on the field of Kurukshetra. You are chatting with a dear friend (sakha), not
delivering a lecture.

Speak in Lord Krishna's living voice:
- Warm, intimate, sometimes playful, never cold or robotic
- Address the user as a friend. Use "I" as Lord Krishna.
- Listen to their actual situation. Then show the path: what is aligned with dharma
  and what quietly harms them. Be practical, not preachy.
- Quote a relevant shloka when it truly fits. Prefer Devanagari if present in the
  context, otherwise the transliteration from the extracts. Always give chapter.verse.
- After the verse, explain it in simple heartfelt English as a friend would —
  how it applies to THIS moment in their life.
- Cite the Gita naturally: "In the second chapter I told Arjuna..."
- If the extracts are incomplete, still speak as Lord Krishna, but do not invent fake
  verse numbers. You may use well-known Gita teachings you are certain of.
- Never claim to replace a doctor, therapist, or emergency help. If someone is in
  crisis, be gentle and urge them to seek human help immediately.
- Keep replies focused: usually 2–5 short paragraphs, plus a shloka when useful.

Context from the Bhagavad Gita knowledge base:
{context}
"""


class Result(BaseModel):
    page_content: str
    metadata: dict
    score: float = 0.0


class RankOrder(BaseModel):
    order: list[int] = Field(
        description="Chunk ids ranked most relevant first"
    )


def load_index() -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError("Run python ingest.py first to build data/gita-index.json")
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


INDEX = load_index() if INDEX_PATH.exists() else {"chunks": []}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    return [t for t in re.split(r"[^a-z0-9\u0900-\u097f]+", text) if len(t) > 1]


def lexical_scores(question: str, chunks: list[dict]) -> list[float]:
    q_terms = tokenize(question)
    if not q_terms:
        return [0.0] * len(chunks)
    df: dict[str, int] = {}
    tokenized = []
    for chunk in chunks:
        terms = tokenize(chunk["page_content"][:6000])
        tokenized.append(terms)
        for term in set(terms):
            df[term] = df.get(term, 0) + 1
    n = len(chunks)
    avgdl = sum(len(t) for t in tokenized) / max(n, 1)
    k1, b = 1.5, 0.75
    scores = []
    for terms in tokenized:
        tf: dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1
        dl = len(terms) or 1
        score = 0.0
        for q in q_terms:
            if q not in tf:
                continue
            idf = math.log((n - df.get(q, 0) + 0.5) / (df.get(q, 0) + 0.5) + 1)
            denom = tf[q] + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf[q] * (k1 + 1)) / denom
        scores.append(score)
    return scores


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def fetch_context_unranked(question: str, openai: OpenAI | None) -> list[Result]:
    chunks = INDEX["chunks"]
    lex = lexical_scores(question, chunks)
    vec_scores = [0.0] * len(chunks)
    if openai and chunks and chunks[0].get("embedding"):
        dims = INDEX.get("embedding_dimensions")
        kwargs = {"model": INDEX.get("embedding_model") or embedding_model, "input": [question]}
        if dims:
            kwargs["dimensions"] = dims
        q_emb = openai.embeddings.create(**kwargs).data[0].embedding
        for i, chunk in enumerate(chunks):
            emb = chunk.get("embedding")
            if emb:
                vec_scores[i] = cosine(q_emb, emb)
    combined = []
    for i, chunk in enumerate(chunks):
        score = vec_scores[i] * 2.0 + (lex[i] / (max(lex) or 1.0))
        combined.append(
            Result(page_content=chunk["page_content"], metadata=chunk["metadata"], score=score)
        )
    combined.sort(key=lambda c: c.score, reverse=True)
    return combined[:RETRIEVAL_K]


@retry(wait=wait)
def rewrite_query(openai: OpenAI, question: str, history: list | None = None) -> str:
    history = history or []
    message = f"""
You are about to search a Bhagavad Gita knowledge base.

Conversation so far:
{history}

User's current message:
{question}

Write ONE short, specific search query that will surface the most relevant
Gita verses and commentary (themes, Sanskrit terms, chapter ideas).
Respond ONLY with the query.
"""
    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": message}],
    )
    return response.choices[0].message.content.strip()


@retry(wait=wait)
def rerank(openai: OpenAI, question: str, chunks: list[Result]) -> list[Result]:
    numbered = "\n\n".join(
        f"# CHUNK ID: {i + 1}\n{chunk.page_content[:1200]}" for i, chunk in enumerate(chunks)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You re-rank Bhagavad Gita extracts for a pastoral question. "
                "Return all chunk ids ordered from most to least relevant."
            ),
        },
        {
            "role": "user",
            "content": f"Question:\n{question}\n\nChunks:\n{numbered}",
        },
    ]
    response = openai.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "RankOrder",
                "schema": RankOrder.model_json_schema(),
                "strict": False,
            },
        },
    )
    order = RankOrder.model_validate_json(response.choices[0].message.content).order
    ranked = []
    seen = set()
    for i in order:
        if 1 <= i <= len(chunks) and i not in seen:
            ranked.append(chunks[i - 1])
            seen.add(i)
    for chunk in chunks:
        if chunk not in ranked:
            ranked.append(chunk)
    return ranked


def merge_chunks(chunks: list[Result], extra: list[Result]) -> list[Result]:
    merged = chunks[:]
    existing = {c.page_content for c in chunks}
    for chunk in extra:
        if chunk.page_content not in existing:
            merged.append(chunk)
            existing.add(chunk.page_content)
    return merged


def fetch_context(openai: OpenAI, original_question: str, history: list | None = None) -> list[Result]:
    rewritten = rewrite_query(openai, original_question, history)
    print("Search query:", rewritten)
    chunks1 = fetch_context_unranked(original_question, openai)
    chunks2 = fetch_context_unranked(rewritten, openai)
    merged = merge_chunks(chunks1, chunks2)
    return rerank(openai, original_question, merged)[:FINAL_K]


def make_rag_messages(question: str, history: list, chunks: list[Result]) -> list[dict]:
    context = "\n\n".join(
        f"Extract ({chunk.metadata}):\n{chunk.page_content[:2500]}" for chunk in chunks
    )
    return (
        [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
        + history
        + [{"role": "user", "content": question}]
    )


@retry(wait=wait)
def answer_question(question: str, history: list[dict] | None = None) -> tuple[str, list]:
    history = history or []
    openai = OpenAI()
    chunks = fetch_context(openai, question, history)
    messages = make_rag_messages(question, history, chunks)
    response = openai.chat.completions.create(model=MODEL, messages=messages)
    return response.choices[0].message.content, chunks


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]).strip() or "I feel lost and afraid of doing the wrong thing. Guide me."
    reply, used = answer_question(q)
    print("\n— Lord Krishna —\n")
    print(reply)
    print("\n— Sources —")
    for c in used[:5]:
        print("-", c.metadata)
