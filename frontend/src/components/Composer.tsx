import { type KeyboardEvent } from "react";
import { SendHorizonal, SlidersHorizontal } from "lucide-react";
import type { SearchMode } from "@/api/types";
import type { QueryFlags } from "@/chat/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  flags: QueryFlags;
  onFlagsChange: (flags: QueryFlags) => void;
}

const SEARCH_MODES: SearchMode[] = ["dense", "sparse", "hybrid"];

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="group relative flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
      <Switch checked={checked} onCheckedChange={onChange} />
      {label}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-60 -translate-x-1/2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-normal leading-snug text-card-foreground opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
      >
        {description}
      </span>
    </label>
  );
}

export function Composer({ value, onChange, onSend, busy, flags, onFlagsChange }: ComposerProps) {
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !busy) onSend();
    }
  }

  const set = <K extends keyof QueryFlags>(key: K, v: QueryFlags[K]) =>
    onFlagsChange({ ...flags, [key]: v });

  return (
    <div className="space-y-2 border-t bg-background/80 p-3 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1 font-medium">
          <SlidersHorizontal className="h-3.5 w-3.5" /> pipeline
        </span>
        <label className="flex items-center gap-1.5">
          search
          <select
            value={flags.search_mode}
            onChange={(e) => set("search_mode", e.target.value as SearchMode)}
            className="rounded-md border border-input bg-background px-1.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {SEARCH_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          top_k
          <input
            type="number"
            min={1}
            max={50}
            value={flags.top_k}
            onChange={(e) =>
              set("top_k", Math.min(50, Math.max(1, Number(e.target.value) || 1)))
            }
            className="w-14 rounded-md border border-input bg-background px-1.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <Toggle
          label="HyDE"
          description="Guesses an answer first, then uses it to search, so it finds the right docs even if your words don't match theirs."
          checked={flags.enable_hyde}
          onChange={(v) => set("enable_hyde", v)}
        />
        <Toggle
          label="rerank"
          description="Sorts the found chunks so the most useful ones come first."
          checked={flags.enable_rerank ?? false}
          onChange={(v) => set("enable_rerank", v)}
        />
        <Toggle
          label="CRAG"
          description="Checks if the found docs are good enough; if not, it searches again or falls back to the web."
          checked={flags.enable_crag}
          onChange={(v) => set("enable_crag", v)}
        />
        <Toggle
          label="Self-RAG"
          description="Double-checks its own answer and tries again if it isn't backed by the docs."
          checked={flags.enable_self_reflective}
          onChange={(v) => set("enable_self_reflective", v)}
        />
      </div>

      <div className="flex items-end gap-2">
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about incidents, pods, runbooks, metrics…  (Enter to send, Shift+Enter for newline)"
          rows={1}
          className={cn("max-h-40", busy && "opacity-60")}
          disabled={busy}
        />
        <Button size="icon" onClick={onSend} disabled={busy || !value.trim()}>
          <SendHorizonal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
