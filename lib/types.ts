export type GitaMetadata = {
  source: string;
  type: string;
  chapter: number | null;
  verses: string | null;
};

export type GitaChunk = {
  id: string;
  page_content: string;
  metadata: GitaMetadata;
  embedding?: number[];
};

export type GitaIndex = {
  embedding_model: string | null;
  embedding_dimensions: number | null;
  chunks: GitaChunk[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type SourceHit = {
  source: string;
  chapter: number | null;
  verses: string | null;
  preview: string;
};

export type QuotedVerse = {
  chapter: number;
  verse: number;
  sanskrit: string;
  transliteration: string;
};
