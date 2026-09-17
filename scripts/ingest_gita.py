"""
Build the Bhagavad Gita knowledge base the same way you learned:

1. Load documents from knowledge-base/
2. Split into overlapping, query-friendly chunks
3. Embed with OpenAI
4. Save a JSON index the chatbot (and Vercel app) can retrieve from

Run:
    python scripts/ingest_gita.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
load_dotenv(ROOT / ".env.local", override=True)

SOURCES_PATH = ROOT / "sources"
KNOWLEDGE_BASE_PATH = ROOT / "knowledge-base"
DATA_PATH = ROOT / "data"
INDEX_PATH = DATA_PATH / "gita-index.json"

embedding_model = "text-embedding-3-small"
EMBEDDING_DIMS = 256
BATCH_SIZE = 64

CHAPTER_TITLES = {
    1: "Arjuna Vishada Yoga — Arjuna's Distress",
    2: "Sankhya Yoga — The Yoga of Knowledge",
    3: "Karma Yoga — The Yoga of Action",
    4: "Jnana Yoga — The Yoga of Wisdom",
    5: "Karma Sannyasa Yoga — Renunciation of Action",
    6: "Dhyana Yoga — The Yoga of Meditation",
    7: "Jnana Vijnana Yoga — Knowledge and Realisation",
    8: "Aksara Brahma Yoga — The Imperishable Absolute",
    9: "Raja Vidya Raja Guhya Yoga — The Royal Secret",
    10: "Vibhuti Yoga — Divine Glories",
    11: "Vishvarupa Darshana Yoga — The Universal Form",
    12: "Bhakti Yoga — The Yoga of Devotion",
    13: "Kshetra Kshetrajna Vibhaga Yoga — Field and Knower",
    14: "Gunatraya Vibhaga Yoga — The Three Gunas",
    15: "Purushottama Yoga — The Supreme Person",
    16: "Daivasura Sampad Vibhaga Yoga — Divine and Demonic",
    17: "Shraddhatraya Vibhaga Yoga — Three Kinds of Faith",
    18: "Moksha Sannyasa Yoga — Liberation and Renunciation",
}


class Result(BaseModel):
    page_content: str
    metadata: dict


class Chunk(BaseModel):
    headline: str = Field(description="A brief heading likely to be surfaced in a query")
    summary: str = Field(description="A few sentences summarizing this chunk")
    original_text: str = Field(description="The original text of this chunk")

    def as_result(self, document: dict) -> Result:
        metadata = {
            "source": document["source"],
            "type": document["type"],
            "chapter": document.get("chapter"),
            "verses": document.get("verses"),
        }
        return Result(
            page_content=self.headline + "\n\n" + self.summary + "\n\n" + self.original_text,
            metadata=metadata,
        )


def clean_page_markers(text: str) -> str:
    text = re.sub(r"\n--- PAGE \d+ ---\n", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def first_sentences(text: str, n: int = 2) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(parts[:n])[:500]


def extract_pdfs() -> None:
    from pypdf import PdfReader

    KNOWLEDGE_BASE_PATH.mkdir(exist_ok=True)
    mapping = {
        "narasingha-gita.pdf": "swami-narasingha.md",
        "boray-gita.pdf": "ttd-boray.md",
    }
    for pdf_name, out_name in mapping.items():
        pdf_path = SOURCES_PATH / pdf_name
        out_path = KNOWLEDGE_BASE_PATH / out_name
        if out_path.exists() and out_path.stat().st_size > 1000:
            print(f"Already extracted: {out_name}")
            continue
        if not pdf_path.exists():
            print(f"Missing PDF: {pdf_name}")
            continue
        reader = PdfReader(str(pdf_path))
        parts = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            parts.append(f"\n\n--- PAGE {i + 1} ---\n\n{t}")
        out_path.write_text("".join(parts), encoding="utf-8")
        print(f"Extracted {pdf_name} -> knowledge-base/{out_name}")


def fetch_documents() -> list[dict]:
    """Homemade DirectoryLoader, same idea as your original ingest.py."""
    documents = []
    if not KNOWLEDGE_BASE_PATH.exists():
        return documents
    for file in sorted(KNOWLEDGE_BASE_PATH.glob("*.md")):
        documents.append(
            {
                "type": file.stem,
                "source": file.as_posix(),
                "text": file.read_text(encoding="utf-8"),
            }
        )
    print(f"Loaded {len(documents)} documents")
    return documents


def chunk_narasingha(raw: str, source: str) -> list[Result]:
    text = clean_page_markers(raw)
    start = re.search(r"VERSE 1\b", text)
    if start:
        preamble = text[: start.start()]
        text = text[start.start() :]
    else:
        preamble = ""

    results: list[Result] = []
    if preamble.strip():
        intro = preamble.strip()[-6000:]
        results.append(
            Result(
                page_content=(
                    "Introduction to Bhagavad-gita (Narasingha commentary)\n\n"
                    "Preface and introductory teachings on approaching the Gita through devotion.\n\n"
                    + intro
                ),
                metadata={
                    "source": "Bhagavad-gita — Swami B.G. Narasingha",
                    "type": "introduction",
                    "chapter": None,
                    "verses": None,
                },
            )
        )

    blocks = re.split(r"\n(?=VERSE\s+[\d\-]+)", text)
    current_chapter = 1
    pending: list[tuple[str, str]] = []

    def flush_pending():
        nonlocal pending
        if not pending:
            return
        verses = ", ".join(v for v, _ in pending)
        body = "\n\n".join(b.strip() for _, b in pending)
        title = CHAPTER_TITLES.get(current_chapter, f"Chapter {current_chapter}")
        headline = f"Gita Chapter {current_chapter}, Verse {verses} — {title}"
        summary = first_sentences(re.sub(r"VERSE\s+[\d\-]+\s*", "", body))
        results.append(
            Result(
                page_content=f"{headline}\n\n{summary}\n\n{body}",
                metadata={
                    "source": "Bhagavad-gita — Swami B.G. Narasingha",
                    "type": "verse",
                    "chapter": current_chapter,
                    "verses": verses,
                },
            )
        )
        pending = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        chapter_hits = [int(c) for c in re.findall(r"Chapter\s+(\d+)", block)]
        if chapter_hits:
            # page headers often repeat; take the max reasonable 1-18
            ch = [c for c in chapter_hits if 1 <= c <= 18]
            if ch and ch[-1] != current_chapter and not pending:
                current_chapter = ch[-1]
            elif ch and ch[-1] > current_chapter:
                flush_pending()
                current_chapter = ch[-1]

        verse_m = re.match(r"VERSE\s+([\d\-]+)", block)
        if not verse_m:
            continue

        verse_id = verse_m.group(1)
        body = block
        anuv_split = re.split(r"\nAnuv[®r]tti\n", body, maxsplit=1)
        verse_body = anuv_split[0].strip()
        commentary = anuv_split[1].strip() if len(anuv_split) > 1 else ""

        pending.append((verse_id, verse_body))
        joined = "\n\n".join(b for _, b in pending)
        if len(joined) >= 900 or commentary:
            flush_pending()

        if commentary:
            # strip trailing next-chapter colophon if present
            commentary = re.split(r"\noµ tat saditi", commentary, maxsplit=1)[0]
            title = CHAPTER_TITLES.get(current_chapter, f"Chapter {current_chapter}")
            windows = overlapping_windows(commentary, 1400, 250)
            for i, window in enumerate(windows, 1):
                headline = f"Commentary on Gita Chapter {current_chapter} — {title} (part {i})"
                summary = first_sentences(window)
                results.append(
                    Result(
                        page_content=f"{headline}\n\n{summary}\n\n{window}",
                        metadata={
                            "source": "Bhagavad-gita — Swami B.G. Narasingha (Anuvritti)",
                            "type": "commentary",
                            "chapter": current_chapter,
                            "verses": verse_id,
                        },
                    )
                )

    flush_pending()
    return results


def overlapping_windows(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(". ", start + size // 2, end)
            if cut > start:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_boray(raw: str, source: str) -> list[Result]:
    text = clean_page_markers(raw)
    results: list[Result] = []

    overview = re.search(r"Overview of Gita Chapters", text)
    if overview:
        overview_text = text[overview.start() : overview.start() + 8000]
        results.append(
            Result(
                page_content=(
                    "Overview of the 18 chapters of the Bhagavad Gita\n\n"
                    "A chapter-by-chapter map of the Gita's teachings.\n\n"
                    + overview_text
                ),
                metadata={
                    "source": "The Bhagavad Gita — Dr. Giridhar Boray (TTD)",
                    "type": "overview",
                    "chapter": None,
                    "verses": None,
                },
            )
        )

    # Split around verse citations like (2.47)
    parts = re.split(r"(?=\n[^\n]{0,400}\(\d+\.\d+\))", text)
    current_chapter = 1
    buffer = []
    buffer_refs: list[str] = []

    def flush():
        nonlocal buffer, buffer_refs
        if not buffer:
            return
        body = "\n\n".join(buffer).strip()
        if len(body) < 80:
            buffer, buffer_refs = [], []
            return
        refs = ", ".join(dict.fromkeys(buffer_refs))
        ch = current_chapter
        title = CHAPTER_TITLES.get(ch, f"Chapter {ch}")
        headline = f"Gita {refs or title} — teaching and comments"
        summary = first_sentences(body)
        results.append(
            Result(
                page_content=f"{headline}\n\n{summary}\n\n{body}",
                metadata={
                    "source": "The Bhagavad Gita — Dr. Giridhar Boray (TTD)",
                    "type": "commentary",
                    "chapter": ch,
                    "verses": refs or None,
                },
            )
        )
        buffer, buffer_refs = [], []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        refs = re.findall(r"\((\d+)\.(\d+)\)", part)
        ch_headers = [int(c) for c in re.findall(r"Chapter\s+(\d+)", part) if 1 <= int(c) <= 18]
        if ch_headers:
            current_chapter = ch_headers[-1]
        if refs:
            current_chapter = int(refs[-1][0])
            buffer_refs.extend(f"{a}.{b}" for a, b in refs[:6])
        buffer.append(part)
        if sum(len(x) for x in buffer) >= 1200:
            flush()
    flush()
    return results


def create_chunks(documents: list[dict]) -> list[Result]:
    chunks: list[Result] = []
    for document in documents:
        name = Path(document["source"]).name.lower()
        if "narasingha" in name:
            chunks.extend(chunk_narasingha(document["text"], document["source"]))
        elif "boray" in name:
            chunks.extend(chunk_boray(document["text"], document["source"]))
        else:
            for i, window in enumerate(overlapping_windows(document["text"], 1400, 250), 1):
                chunks.append(
                    Result(
                        page_content=window,
                        metadata={
                            "source": document["source"],
                            "type": document.get("type", "other"),
                            "chapter": None,
                            "verses": None,
                        },
                    )
                )
    print(f"Created {len(chunks)} chunks")
    return chunks


def embed_texts(openai: OpenAI, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in tqdm(range(0, len(texts), BATCH_SIZE), desc="Embedding"):
        batch = texts[i : i + BATCH_SIZE]
        emb = openai.embeddings.create(
            model=embedding_model,
            input=batch,
            dimensions=EMBEDDING_DIMS,
        ).data
        vectors.extend([e.embedding for e in emb])
    return vectors


def save_index(chunks: list[Result], vectors: list[list[float]] | None) -> None:
    DATA_PATH.mkdir(exist_ok=True)
    payload = {
        "embedding_model": embedding_model if vectors else None,
        "embedding_dimensions": EMBEDDING_DIMS if vectors else None,
        "chunks": [],
    }
    for i, chunk in enumerate(chunks):
        item = {
            "id": str(i),
            "page_content": chunk.page_content,
            "metadata": chunk.metadata,
        }
        if vectors:
            item["embedding"] = vectors[i]
        payload["chunks"].append(item)
    INDEX_PATH.write_text(json.dumps(payload), encoding="utf-8")
    print(f"Wrote {INDEX_PATH} ({INDEX_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    extract_pdfs()
    documents = fetch_documents()
    chunks = create_chunks(documents)

    vectors = None
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        openai = OpenAI()
        texts = [c.page_content[:8000] for c in chunks]
        vectors = embed_texts(openai, texts)
        print(f"Embedded {len(vectors)} chunks")
    else:
        print("No OPENAI_API_KEY — saving lexical index only. Add a key and re-run for vector RAG.")

    save_index(chunks, vectors)
    print("Ingestion complete")
