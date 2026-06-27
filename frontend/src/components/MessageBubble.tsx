import Markdown from "react-markdown";
import { Database, Lightbulb, RefreshCw, Zap } from "lucide-react";
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

  const { response, error } = message;

  // In flight
  if (!response && !error) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        Working through the pipeline…
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
          {response.sources.length > 0 && (
            <Badge variant="outline">{response.sources.length} sources</Badge>
          )}
        </div>
      </button>
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
