import fs from "fs";
import path from "path";

export type CleanVerse = {
  chapter: number;
  verse: number;
  sanskrit: string;
  transliteration: string;
};

let cached: Map<string, CleanVerse> | null = null;

function loadMap(): Map<string, CleanVerse> {
  if (cached) return cached;
  const file = path.join(process.cwd(), "data", "gita-verses.json");
  const rows = JSON.parse(fs.readFileSync(file, "utf8")) as CleanVerse[];
  cached = new Map(rows.map((v) => [`${v.chapter}.${v.verse}`, v]));
  return cached;
}

export function verseKey(chapter: number, verse: number): string {
  return `${chapter}.${verse}`;
}

export function getVerse(chapter: number, verse: number): CleanVerse | null {
  return loadMap().get(verseKey(chapter, verse)) || null;
}

export function parseVerseRefs(chapter: number | null, verses: string | null): { chapter: number; verse: number }[] {
  if (!verses) {
    return [];
  }
  const refs: { chapter: number; verse: number }[] = [];
  const dotted = [...verses.matchAll(/(\d+)\.(\d+)/g)];
  if (dotted.length) {
    for (const m of dotted) {
      refs.push({ chapter: Number(m[1]), verse: Number(m[2]) });
    }
    return refs;
  }
  if (!chapter) return [];
  for (const part of verses.split(",")) {
    const range = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!range) continue;
    const start = Number(range[1]);
    const end = range[2] ? Number(range[2]) : start;
    for (let v = start; v <= end && v - start < 6; v++) {
      refs.push({ chapter, verse: v });
    }
  }
  return refs;
}

export function versesForChunks(
  chunks: { metadata: { chapter: number | null; verses: string | null } }[],
  limit = 4
): CleanVerse[] {
  const seen = new Set<string>();
  const out: CleanVerse[] = [];
  for (const chunk of chunks) {
    for (const ref of parseVerseRefs(chunk.metadata.chapter, chunk.metadata.verses)) {
      const key = verseKey(ref.chapter, ref.verse);
      if (seen.has(key)) continue;
      const verse = getVerse(ref.chapter, ref.verse);
      if (!verse) continue;
      seen.add(key);
      out.push(verse);
      if (out.length >= limit) return out;
    }
  }
  return out;
}

export function formatCleanShlokas(verses: CleanVerse[]): string {
  if (!verses.length) return "";
  return verses
    .map(
      (v) =>
        `BG ${v.chapter}.${v.verse}\n${v.sanskrit}\n${v.transliteration}`
    )
    .join("\n\n");
}
