import OpenAI from "openai";
import { buildContext, KRISHNA_SYSTEM, toOpenAIHistory } from "@/lib/krishna-prompt";
import { loadIndex, mergeUnique, retrieve } from "@/lib/retrieve";
import type { ChatMessage, SourceHit } from "@/lib/types";
import { formatCleanShlokas, versesForChunks } from "@/lib/gita-verses";

export const runtime = "nodejs";
export const maxDuration = 60;

const MODEL = process.env.KRISHNA_MODEL || "gpt-4o-mini";

function previewOf(text: string): string {
  return text
    .replace(/[\uE000-\uF8FF]/g, "")
    .replace(/[\u0900-\u097F]+/g, " ")
    .replace(/\s+/g, " ")
    .slice(0, 180)
    .trim();
}

export async function POST(req: Request) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return Response.json(
      { error: "Add OPENAI_API_KEY to .env.local (and to Vercel env vars when you deploy)." },
      { status: 500 }
    );
  }

  const body = (await req.json()) as { messages?: ChatMessage[] };
  const messages = body.messages || [];
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUser?.content?.trim()) {
    return Response.json({ error: "Say something to Lord Krishna first." }, { status: 400 });
  }

  const openai = new OpenAI({ apiKey });
  const index = loadIndex();
  const history = toOpenAIHistory(messages.slice(0, -1));

  const rewrite = await openai.chat.completions.create({
    model: MODEL,
    temperature: 0,
    max_tokens: 80,
    messages: [
      {
        role: "system",
        content:
          "Rewrite the user's message as a short Bhagavad Gita search query (themes, verses, Sanskrit ideas). Reply with the query only.",
      },
      {
        role: "user",
        content: `History: ${JSON.stringify(history)}\n\nMessage: ${lastUser.content}`,
      },
    ],
  });
  const rewritten = rewrite.choices[0]?.message?.content?.trim() || lastUser.content;

  let queryEmbedding: number[] | undefined;
  if (index.chunks[0]?.embedding && index.embedding_model) {
    const emb = await openai.embeddings.create({
      model: index.embedding_model,
      input: `${lastUser.content}\n${rewritten}`,
      ...(index.embedding_dimensions
        ? { dimensions: index.embedding_dimensions }
        : {}),
    });
    queryEmbedding = emb.data[0].embedding;
  }

  const chunks = mergeUnique(
    retrieve(lastUser.content, queryEmbedding, 12),
    retrieve(rewritten, queryEmbedding, 12)
  ).slice(0, 10);

  const quotedVerses = versesForChunks(chunks);
  const context = buildContext(chunks, formatCleanShlokas(quotedVerses));
  const sources: SourceHit[] = chunks.slice(0, 6).map((c) => ({
    source: c.metadata.source,
    chapter: c.metadata.chapter,
    verses: c.metadata.verses,
    preview: previewOf(c.page_content),
  }));

  const stream = await openai.chat.completions.create({
    model: MODEL,
    temperature: 0.7,
    stream: true,
    messages: [
      { role: "system", content: `${KRISHNA_SYSTEM}\n\nGita knowledge-base extracts:\n${context}` },
      ...history,
      { role: "user", content: lastUser.content },
    ],
  });

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      controller.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: "sources", sources, verses: quotedVerses })}\n\n`)
      );
      try {
        for await (const part of stream) {
          const token = part.choices[0]?.delta?.content;
          if (token) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "token", text: token })}\n\n`));
          }
        }
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "done" })}\n\n`));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Lord Krishna could not reply.";
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "error", error: message })}\n\n`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}
