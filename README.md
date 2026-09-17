# Gita Sakha

Talk with **Lord Krishna**. A Vercel-ready Next.js chatbot that answers as a friend, using RAG over your Bhagavad Gita books plus clean Unicode shlokas.

## Project structure

```text
app/                  Next.js UI and API
  page.tsx            Chat screen (Lord Krishna left, you right)
  layout.tsx
  globals.css
  api/chat/route.ts   RAG + OpenAI streaming reply
lib/
  krishna-prompt.ts   Lord Krishna voice and context builder
  retrieve.ts         Search over Gita chunks
  gita-verses.ts      Clean Devanagari shloka lookup
  types.ts
data/
  gita-index.json     Chunked commentary for RAG (needed to run)
  gita-verses.json    Readable Sanskrit verses
public/
  krishna-portrait.png
scripts/
  ingest_gita.py      Extract PDFs → chunks → optional embeddings
  ask_krishna.py      Terminal RAG chat
sources/              Your PDFs (not pushed)
knowledge-base/       Extracted text (not pushed; rebuilt by ingest)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/ingest_gita.py
```

```bash
cp .env.example .env.local
# add OPENAI_API_KEY
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Deploy on Vercel

1. Push this repo (PDFs and `.env` stay local).
2. Import as a Next.js project.
3. Set `OPENAI_API_KEY`.
4. Deploy.

## Python CLI

```bash
python scripts/ask_krishna.py "I am scared I am wasting my life."
```
