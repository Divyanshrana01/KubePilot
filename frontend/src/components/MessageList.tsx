import { useEffect, useRef } from "react";
import { Boxes } from "lucide-react";
import type { ChatMessage, QueryFlags } from "@/chat/types";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
  activeId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onApproveSql: (queryId: string, approved: boolean) => Promise<void>;
  onRetry: (question: string, newFlags: QueryFlags) => void;
}

const EXAMPLES = [
  "Why are pods in the payments namespace stuck in CrashLoopBackOff?",
  "Summarize the runbook for an etcd disk-pressure incident.",
  "How many P1 incidents did we have last week?",
];

export function MessageList({
  messages,
  activeId,
  busy,
  onSelect,
  onApproveSql,
  onRetry,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view as the conversation grows.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/15">
          <Boxes className="h-7 w-7 text-primary" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">Ask about your cluster</h2>
          <p className="text-sm text-muted-foreground">
            Incidents, pod failures, runbooks, or live metrics.
          </p>
        </div>
        <div className="flex max-w-md flex-col gap-2">
          {EXAMPLES.map((ex) => (
            <div
              key={ex}
              className="rounded-lg border bg-card px-3 py-2 text-left text-sm text-muted-foreground"
            >
              {ex}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          isActive={m.id === activeId}
          busy={busy}
          onSelect={() => onSelect(m.id)}
          onApproveSql={onApproveSql}
          onRetry={onRetry}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}
