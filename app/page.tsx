"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ChatMessage, QuotedVerse, SourceHit } from "@/lib/types";

type ThreadItem = ChatMessage & { sources?: SourceHit[]; verses?: QuotedVerse[] };

const SUGGESTIONS = [
  "I am anxious about my career. What should I do?",
  "I get angry at people I love. How do I stop?",
  "I feel guilty for choosing my own path.",
  "What is dharma when every option looks messy?",
];

function ShlokaCard({ verse }: { verse: QuotedVerse }) {
  return (
    <div className="shloka">
      <div className="shloka-ref">Bhagavad Gita {verse.chapter}.{verse.verse}</div>
      <div className="shloka-sanskrit">{verse.sanskrit.replace(/।।[\d.]+।।/g, "").trim()}</div>
      {verse.transliteration ? <div className="shloka-latin">{verse.transliteration}</div> : null}
    </div>
  );
}

function KrishnaBody({ text, verses }: { text: string; verses?: QuotedVerse[] }) {
  const parts: { type: "text" | "shloka"; value: string; ref?: string }[] = [];
  const re = /\[shloka\s+(\d+\.\d+)\]([\s\S]*?)\[\/shloka\]/gi;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) {
    if (match.index > last) {
      parts.push({ type: "text", value: text.slice(last, match.index) });
    }
    parts.push({ type: "shloka", ref: match[1], value: match[2].trim() });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });

  const usedInline = parts.some((p) => p.type === "shloka");

  return (
    <>
      {!usedInline && verses?.length
        ? verses.map((v) => <ShlokaCard key={`${v.chapter}.${v.verse}`} verse={v} />)
        : null}
      {parts.map((part, i) => {
        if (part.type === "text") {
          const cleaned = part.value
            .replace(/[\uE000-\uF8FF]/g, "")
            .replace(/[\u0900-\u097F]+/g, " ")
            .replace(/[ \t]{2,}/g, " ");
          return cleaned.trim() ? <span key={i}>{cleaned}</span> : null;
        }
        const [chapter, verse] = (part.ref || "0.0").split(".").map(Number);
        const known = verses?.find((v) => v.chapter === chapter && v.verse === verse);
        if (known) return <ShlokaCard key={i} verse={known} />;
        const looksBroken = /[\uE000-\uF8FF]/.test(part.value) || !/[\u0900-\u097F]{8,}/.test(part.value);
        if (looksBroken) return null;
        return (
          <ShlokaCard
            key={i}
            verse={{ chapter, verse, sanskrit: part.value, transliteration: "" }}
          />
        );
      })}
    </>
  );
}

export default function HomePage() {
  const [messages, setMessages] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const canSend = useMemo(() => input.trim().length > 0 && !busy, [input, busy]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: ThreadItem[] = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError("");

    const assistant: ThreadItem = { role: "assistant", content: "" };
    setMessages([...next, assistant]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });
      if (!res.ok || !res.body) {
        const payload = await res.json().catch(() => ({ error: "Lord Krishna is silent right now." }));
        throw new Error(payload.error || "Request failed");
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let reply = "";
      let sources: SourceHit[] = [];
      let verses: QuotedVerse[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const line = event.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const payload = JSON.parse(line.slice(6)) as {
            type: string;
            text?: string;
            sources?: SourceHit[];
            verses?: QuotedVerse[];
            error?: string;
          };
          if (payload.type === "sources") {
            if (payload.sources) sources = payload.sources;
            if (payload.verses) verses = payload.verses;
          }
          if (payload.type === "token" && payload.text) reply += payload.text;
          if (payload.type === "error") throw new Error(payload.error);
          setMessages([...next, { role: "assistant", content: reply, sources, verses }]);
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
      setMessages(next);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  return (
    <div className="app">
      <aside className="krishna-side">
        <div className="kicker">Gita Sakha</div>
        <img className="portrait" src="/krishna-portrait.png" alt="Lord Krishna" />
        <h1>Lord Krishna</h1>
        <p className="subtitle">
          Your friend from Kurukshetra. Speak as you are. I will answer from the Gita — verses,
          meaning, and what is worth doing now.
        </p>
        <p className="blessing">“I am the friend of every being. Come, sit. Tell me what weighs on you.”</p>
        <div className="chapters">
          {Array.from({ length: 18 }, (_, i) => (
            <span key={i}>Ch. {i + 1}</span>
          ))}
        </div>
      </aside>

      <main className="chat-side">
        <header className="chat-header">
          <strong>Gita Sakha</strong>
          <span>You on the right · Lord Krishna on the left</span>
        </header>

        <div className="thread">
          {messages.length === 0 && (
            <div className="msg krishna">
              <span className="who">Lord Krishna</span>
              Friend, the battlefield is often inside the heart. Speak freely — duty, fear, love,
              confusion. I will not give you empty comfort. I will give you a path, with the Gita as
              witness.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role === "user" ? "user" : "krishna"}`}>
              <span className="who">{m.role === "user" ? "You" : "Lord Krishna"}</span>
              {m.role === "assistant" ? (
                <KrishnaBody text={m.content} verses={m.verses} />
              ) : (
                m.content
              )}
              {m.role === "assistant" && m.sources?.length ? (
                <div className="sources">
                  From the Gita
                  {m.sources.map((s, j) => (
                    <div key={j}>
                      {s.chapter ? `Chapter ${s.chapter}` : s.source}
                      {s.verses ? ` · ${s.verses}` : ""}
                      {s.preview ? ` — ${s.preview}` : ""}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          {busy && messages.at(-1)?.role === "user" ? (
            <div className="msg krishna">
              <span className="who">Lord Krishna</span>
              Listening…
            </div>
          ) : null}
          <div ref={bottom} />
        </div>

        {error ? <div className="error">{error}</div> : null}

        {messages.length === 0 ? (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        ) : null}

        <form className="composer" onSubmit={onSubmit}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Tell Lord Krishna what is happening…"
            rows={2}
          />
          <button type="submit" disabled={!canSend}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
