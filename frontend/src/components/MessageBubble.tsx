import { useState } from "react";
import Markdown from "react-markdown";
import { ChevronDown, Database, ExternalLink, FileText, Lightbulb, RefreshCw, Zap } from "lucide-react";
import type { ChatResponse } from "@/api/types";
import type { ChatMessage, QueryFlags } from "@/chat/types";
import { applySuggestions, suggestImprovements, type Suggestion } from "@/chat/suggestions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { SqlApprovalCard } from "./SqlApprovalCard";

interface MessageBubbleProps {
  message: ChatMessage;
  isActive: boolean;
  busy: boolean;
  onSelect: () => void;
  onApproveSql: (queryId: string, approved: boolean) => Promise<void>;
  onRetry: (question: string, newFlags: QueryFlags) => void;
}

// Human-readable labels for the pipeline stages streamed over SSE.
const STAGE_LABELS: Record<string, string> = {
  routing: "Routing your question…",
  retrieving: "Retrieving documents…",
  grading: "Grading relevance (CRAG)…",
  generating: "Generating answer…",
};

// Shown under a weak answer: lists pipeline options that might help and offers a
// one-click re-run with them switched on.
function SuggestionBar({
  suggestions,
  busy,
  onApply,
}: {
  suggestions: Suggestion[];
  busy: boolean;
  onApply: () => void;
}) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-amber-500">
        <Lightbulb className="h-3.5 w-3.5" />
        This answer may be weak. These options could help:
      </div>
      <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
        {suggestions.map((s) => (
          <li key={s.label}>
            <span className="font-medium text-foreground">{s.label}</span>: {s.reason}
          </li>
        ))}
      </ul>
      <Button size="sm" variant="outline" className="mt-2" disabled={busy} onClick={onApply}>
        <RefreshCw className="h-3.5 w-3.5" />
        Retry with {suggestions.map((s) => s.label).join(" + ")}
      </Button>
    </div>
  );
}

// Collapsible disclosure that reveals the SQL that was generated/run to answer the question.
function SqlDisclosure({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <Database className="h-3.5 w-3.5" />
        View SQL query
        <ChevronDown className={cn("ml-auto h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <pre className="overflow-x-auto border-t border-border px-3 py-2 text-xs leading-relaxed">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  );
}

// A source string is rendered as a real link when it looks like a URL (e.g. web-search
// fallback results), otherwise as plain text (local document / table names aren't links).
function SourceLabel({ source }: { source: string }) {
  const isUrl = /^https?:\/\//i.test(source);
  if (isUrl) {
    return (
      <a
        href={source}
        target="_blank"
        rel="noopener noreferrer"
        title={source}
        className="inline-flex min-w-0 items-center gap-1 truncate text-xs font-medium text-primary hover:underline"
      >
        <span className="truncate">{source}</span>
        <ExternalLink className="h-3 w-3 shrink-0" />
      </a>
    );
  }
  return (
    <span className="truncate text-xs font-medium" title={source}>
      {source}
    </span>
  );
}

// Collapsible "N sources" disclosure: lists the retrieved chunks (source + relevance score
// + snippet) so the user can actually see and open what the answer was grounded on.
function SourcesDisclosure({ response }: { response: ChatResponse }) {
  const [open, setOpen] = useState(false);
  const chunks = response.metadata.retrieved_chunks;
  const count = response.sources.length;
  return (
    <div className="rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <FileText className="h-3.5 w-3.5" />
        {count} source{count === 1 ? "" : "s"}
        <ChevronDown className={cn("ml-auto h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-3 py-2">
          {chunks.length > 0
            ? chunks.map((c, i) => (
                <div key={i} className="rounded-md bg-muted/40 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <SourceLabel source={c.source || "unknown"} />
                    <Badge variant="outline">{c.score.toFixed(3)}</Badge>
                  </div>
                  <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{c.text}</p>
                </div>
              ))
            : response.sources.map((s, i) => (
                <div key={i} className="flex">
                  <SourceLabel source={s} />
                </div>
              ))}
        </div>
      )}
    </div>
  );
}

export function MessageBubble({
  message,
  isActive,
  busy,
  onSelect,
  onApproveSql,
  onRetry,
}: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.text}
        </div>
      </div>
    );
  }

  const { response, error, stage, streamedText } = message;

  // In flight: show the current pipeline stage, then stream the answer text as tokens arrive.
  if (!response && !error) {
    return (
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-card px-4 py-3 text-sm">
        {streamedText ? (
          <div className="prose-chat">
            <Markdown>{streamedText}</Markdown>
            <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse rounded-sm bg-primary align-middle" />
          </div>
        ) : (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner />
            {STAGE_LABELS[stage ?? "routing"] ?? "Working…"}
          </div>
        )}
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (!response) return null;

  if (response.pending_sql) {
    return (
      <div className="max-w-[85%]">
        <SqlApprovalCard
          block={response.pending_sql}
          onDecision={(approved) => onApproveSql(response.pending_sql!.query_id, approved)}
        />
      </div>
    );
  }

  const confidencePct = Math.round(response.confidence * 100);
  const suggestions = suggestImprovements(response, message.flags);

  return (
    <div className="max-w-[85%] space-y-2">
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "block w-full rounded-2xl rounded-bl-sm border bg-card px-4 py-3 text-left text-sm transition-colors hover:border-primary/40",
          isActive ? "border-primary/60 ring-1 ring-primary/30" : "border-border",
        )}
      >
        <div className="prose-chat">
          <Markdown>{response.answer || "_(empty answer)_"}</Markdown>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Badge variant={response.metadata.route === "sql" ? "warning" : "secondary"}>
            {response.metadata.route === "sql" ? <Database className="mr-1 h-3 w-3" /> : null}
            {response.metadata.route}
          </Badge>
          <Badge
            variant={confidencePct >= 80 ? "success" : confidencePct >= 50 ? "warning" : "destructive"}
          >
            {confidencePct}% confidence
          </Badge>
          {response.cache_hit && (
            <Badge variant="default">
              <Zap className="mr-1 h-3 w-3" />
              cache hit
            </Badge>
          )}
        </div>
      </button>
      {response.metadata.route !== "sql" && response.sources.length > 0 && (
        <SourcesDisclosure response={response} />
      )}
      {response.metadata.route === "sql" && response.metadata.executed_sql && (
        <SqlDisclosure sql={response.metadata.executed_sql} />
      )}
      {suggestions.length > 0 && (
        <SuggestionBar
          suggestions={suggestions}
          busy={busy}
          onApply={() => onRetry(message.question, applySuggestions(message.flags, suggestions))}
        />
      )}
    </div>
  );
}
