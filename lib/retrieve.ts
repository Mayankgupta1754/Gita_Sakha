import fs from "fs";
import path from "path";
import type { GitaChunk, GitaIndex } from "./types";

let cached: GitaIndex | null = null;

export function loadIndex(): GitaIndex {
  if (cached) return cached;
  const file = path.join(process.cwd(), "data", "gita-index.json");
  cached = JSON.parse(fs.readFileSync(file, "utf8")) as GitaIndex;
  return cached;
}

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9\u0900-\u097f]+/)
    .filter((t) => t.length > 1);
}

function lexicalScores(question: string, chunks: GitaChunk[]): number[] {
  const qTerms = tokenize(question);
  if (!qTerms.length) return chunks.map(() => 0);
  const tokenized = chunks.map((c) => tokenize(c.page_content.slice(0, 6000)));
  const df = new Map<string, number>();
  for (const terms of tokenized) {
    for (const term of new Set(terms)) {
      df.set(term, (df.get(term) || 0) + 1);
    }
  }
  const n = chunks.length;
  const avgdl = tokenized.reduce((s, t) => s + t.length, 0) / Math.max(n, 1);
  const k1 = 1.5;
  const b = 0.75;
  return tokenized.map((terms) => {
    const tf = new Map<string, number>();
    for (const t of terms) tf.set(t, (tf.get(t) || 0) + 1);
    const dl = terms.length || 1;
    let score = 0;
    for (const q of qTerms) {
      const f = tf.get(q);
      if (!f) continue;
      const nq = df.get(q) || 0;
      const idf = Math.log((n - nq + 0.5) / (nq + 0.5) + 1);
      score += (idf * (f * (k1 + 1))) / (f + k1 * (1 - b + b * (dl / avgdl)));
    }
    return score;
  });
}

function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / ((Math.sqrt(na) || 1) * (Math.sqrt(nb) || 1));
}

export function retrieve(question: string, queryEmbedding?: number[], k = 12): GitaChunk[] {
  const { chunks } = loadIndex();
  const lex = lexicalScores(question, chunks);
  const maxLex = Math.max(...lex, 1e-6);
  const scored = chunks.map((chunk, i) => {
    let vec = 0;
    if (queryEmbedding && chunk.embedding?.length) {
      vec = cosine(queryEmbedding, chunk.embedding);
    }
    return { chunk, score: vec * 2 + lex[i] / maxLex };
  });
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k).map((s) => s.chunk);
}

export function mergeUnique(a: GitaChunk[], b: GitaChunk[]): GitaChunk[] {
  const seen = new Set<string>();
  const out: GitaChunk[] = [];
  for (const chunk of [...a, ...b]) {
    if (seen.has(chunk.id)) continue;
    seen.add(chunk.id);
    out.push(chunk);
  }
  return out;
}
