"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useMe } from "@/lib/hooks";
import type { ChatMessage } from "@/lib/types";
import { cn, isoDate } from "@/lib/utils";
import { Logo } from "@/components/app-shell";
import { ConfirmCard } from "@/components/chat/confirm-card";
import { FormError } from "@/components/ui/alert";
import { Skeleton } from "@/components/spinner";

const SUGGESTIONS = [
  "Slept 6 hours, studied 2h this evening",
  "How has my week been so far?",
  "Decided to skip the gym tonight, feeling drained",
  "Why might I be tired today?",
];
const MAX = 2000;

export default function ChatPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const history = useQuery({ queryKey: qk.chat, queryFn: () => api.chatHistory(100) });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null); // twin text in progress
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    if (history.data && !loaded.current) {
      loaded.current = true;
      setMessages(history.data);
    }
  }, [history.data]);

  // Mirror local state into the query cache so returning to this page shows everything.
  useEffect(() => {
    if (loaded.current) qc.setQueryData(qk.chat, messages.filter((m) => !m.id.startsWith("temp-")));
  }, [messages, qc]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Keep the newest content in view.
  useLayoutEffect(() => {
    endRef.current?.scrollIntoView({ behavior: loaded.current ? "smooth" : "auto", block: "end" });
  }, [messages, streaming, busy]);

  const replaceMessage = useCallback((m: ChatMessage) => {
    setMessages((list) => list.map((x) => (x.id === m.id ? m : x)));
  }, []);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setError(null);
    setDraft("");
    setBusy(true);
    setStreaming(null);
    const tempId = `temp-${Date.now()}`;
    setMessages((list) => [
      ...list,
      {
        id: tempId, role: "user", text: message, created_at: new Date().toISOString(),
        learnable: true, extraction: null, extraction_status: null,
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let userId = tempId;
    try {
      await api.sendChat(message, isoDate(), (e) => {
        switch (e.type) {
          case "user_message":
            userId = e.message.id;
            setMessages((list) => list.map((x) => (x.id === tempId ? e.message : x)));
            break;
          case "extraction":
            setMessages((list) =>
              list.map((x) =>
                x.id === e.message_id
                  ? { ...x, extraction: e.card, extraction_status: "pending" }
                  : x,
              ),
            );
            break;
          case "token":
            setStreaming((s) => (s ?? "") + e.text);
            break;
          case "done":
            setStreaming(null);
            setMessages((list) => [...list, e.message]);
            break;
          case "error":
            setStreaming(null);
            setError(e.detail);
            break;
        }
      }, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
        // The message never reached the server: put it back in the box.
        if (userId === tempId) {
          setMessages((list) => list.filter((x) => x.id !== tempId));
          setDraft(message);
        }
      }
      setStreaming(null);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  const categories = me?.profile.categories ?? [];
  const thinking = busy && streaming === null;
  const firstName = me?.user.name.split(" ")[0];

  return (
    <div className="flex min-h-[calc(100dvh-12rem)] flex-col md:min-h-[calc(100dvh-6rem)]">
      <div className="mb-6">
        <p className="eyebrow mb-2 text-primary">Your twin</p>
        <h1 className="text-[28px] font-semibold leading-tight md:text-[32px]">
          {firstName ? `Talk to me, ${firstName}` : "Chat"}
        </h1>
      </div>

      <div className="flex flex-1 flex-col gap-5 pb-6" aria-live="polite" aria-busy={busy}>
        {history.isLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="ml-auto h-12 w-2/3" />
            <Skeleton className="h-20 w-3/4" />
          </div>
        ) : history.error ? (
          <FormError message={history.error.message} />
        ) : messages.length === 0 ? (
          <Welcome onPick={(s) => send(s)} disabled={busy} />
        ) : (
          messages.map((m) => (
            <div key={m.id} className="flex flex-col gap-2">
              <Bubble message={m} />
              {m.role === "user" && m.extraction && (
                <div className="ml-auto w-full max-w-xl">
                  <ConfirmCard
                    key={`${m.id}:${m.extraction_status}`}
                    message={m}
                    categories={categories}
                    onUpdated={replaceMessage}
                  />
                </div>
              )}
            </div>
          ))
        )}

        {streaming !== null && (
          <Bubble
            message={{
              id: "streaming", role: "twin", text: streaming, created_at: "", learnable: false,
              extraction: null, extraction_status: null,
            }}
            streaming
          />
        )}
        {thinking && <Thinking />}
        {error && <FormError message={error} />}
        {/* scroll margin = composer (+ bottom nav on phones), so the newest message is never hidden */}
        <div ref={endRef} className="scroll-mb-48 md:scroll-mb-32" />
      </div>

      <Composer
        value={draft}
        onChange={setDraft}
        onSend={() => send(draft)}
        disabled={busy}
      />
    </div>
  );
}

function Bubble({ message: m, streaming = false }: { message: ChatMessage; streaming?: boolean }) {
  const mine = m.role === "user";
  return (
    <div className={cn("flex animate-fade-up items-end gap-2.5", mine && "justify-end")}>
      {!mine && (
        <div className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card">
          <Logo className="h-4 w-4" />
        </div>
      )}
      <div className={cn("flex max-w-[85%] flex-col gap-1 md:max-w-[75%]", mine && "items-end")}>
        <div
          className={cn(
            "whitespace-pre-wrap break-words rounded-lg px-4 py-2.5 text-[15px] leading-relaxed",
            mine
              ? "rounded-br-sm bg-primary-soft text-foreground ring-1 ring-primary/15"
              : "rounded-bl-sm border bg-card shadow-card",
          )}
        >
          {m.text}
          {streaming && (
            <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-primary" aria-hidden />
          )}
        </div>
        {mine && !m.learnable && (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <EyeOff className="h-3 w-3" aria-hidden /> Saved, not used for learning
          </span>
        )}
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex animate-fade-in items-center gap-2.5" role="status">
      <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-card">
        <Logo className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-1.5 rounded-lg rounded-bl-sm border bg-card px-4 py-3 shadow-card">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/70"
            style={{ animationDelay: `${i * 140}ms` }}
          />
        ))}
        <span className="ml-1.5 text-xs text-muted-foreground">Twin is thinking</span>
      </div>
    </div>
  );
}

function Welcome({ onPick, disabled }: { onPick: (s: string) => void; disabled: boolean }) {
  return (
    <div className="animate-fade-up rounded-lg border bg-card p-6 shadow-card md:p-8">
      <div className="flex items-start gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-primary-soft">
          <Logo className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold">Tell me about your day</h2>
          <p className="mt-1 max-w-lg text-sm leading-relaxed text-muted-foreground">
            Write the way you&apos;d text a friend. I&apos;ll pick out sleep, mood, activities and
            decisions for you to confirm, and I remember what you tell me.
          </p>
        </div>
      </div>
      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s, i) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="animate-fade-up rounded-md border bg-background px-3.5 py-3 text-left text-sm transition-[border-color,background-color,transform] duration-150 hover:border-primary/40 hover:bg-primary-soft/50 active:scale-[0.99] disabled:opacity-50"
            style={{ animationDelay: `${80 + i * 50}ms` }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const over = value.length > MAX;
  return (
    <div className="sticky bottom-[calc(4rem+env(safe-area-inset-bottom))] z-10 -mx-4 border-t bg-background/95 px-4 pb-3 pt-3 backdrop-blur md:bottom-0 md:mx-0 md:border-0 md:bg-transparent md:px-0 md:pb-4 md:backdrop-blur-0">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!over) onSend();
        }}
        className="flex items-end gap-2 rounded-lg border bg-card p-2 shadow-lift transition-[border-color,box-shadow] focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10"
      >
        <label htmlFor="chat-input" className="sr-only">
          Message your twin
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (!disabled && !over) onSend();
            }
          }}
          placeholder="How was today? e.g. slept 6h, studied 2 hours…"
          className="max-h-[180px] min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed placeholder:text-muted-foreground/70 focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim() || over}
          aria-label="Send"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition-[background-color,transform,opacity] duration-150 hover:bg-[hsl(17_86%_35%)] active:scale-95 disabled:opacity-35"
        >
          <ArrowUp className="h-5 w-5" strokeWidth={2.4} />
        </button>
      </form>
      <div className="mt-1.5 flex justify-between px-1 text-[11px] text-muted-foreground">
        <span>Enter to send · Shift+Enter for a new line</span>
        {value.length > MAX - 200 && (
          <span className={cn("font-mono", over && "text-destructive")}>
            {value.length}/{MAX}
          </span>
        )}
      </div>
    </div>
  );
}
