import type { ChatResponse } from "@/api/types";
import type { QueryFlags } from "./types";

// A single nudge: a flag change plus a plain-language reason it might help.
// Applying `patch` flips one pipeline option toward "more thorough".
export interface Suggestion {
  label: string;
  reason: string;
  patch: Partial<QueryFlags>;
}

// Below this confidence (or with no sources at all) we treat an answer as
// "not so good" and offer ways to improve it. Mirrors the badge thresholds
// used in MessageBubble.
const WEAK_CONFIDENCE = 0.6;

export function isWeakResult(response: ChatResponse): boolean {
  // SQL answers don't go through retrieval, so the retrieval toggles can't help them.
  if (response.metadata.route === "sql") return false;
  return response.confidence < WEAK_CONFIDENCE || response.sources.length === 0;
}

// Given a weak answer and the flags that produced it, suggest pipeline options
// that are currently off and could plausibly improve a re-run. Ordered by impact
// and capped so the nudge stays focused.
export function suggestImprovements(response: ChatResponse, flags: QueryFlags): Suggestion[] {
  if (!isWeakResult(response)) return [];

  const out: Suggestion[] = [];

  if (!flags.enable_rerank)
    out.push({
      label: "rerank",
      reason: "put the most relevant passages first",
      patch: { enable_rerank: true },
    });

  if (!flags.enable_hyde)
    out.push({
      label: "HyDE",
      reason: "find docs even when they use different words",
      patch: { enable_hyde: true },
    });

  if (!flags.enable_crag)
    out.push({
      label: "CRAG",
      reason: "re-search or check the web when docs look weak",
      patch: { enable_crag: true },
    });

  if (flags.search_mode !== "hybrid")
    out.push({
      label: "hybrid search",
      reason: "combine keyword and meaning-based search",
      patch: { search_mode: "hybrid" },
    });

  if (flags.top_k < 8)
    out.push({
      label: "more sources",
      reason: "retrieve more chunks to draw from",
      patch: { top_k: 8 },
    });

  if (!flags.enable_self_reflective)
    out.push({
      label: "Self-RAG",
      reason: "let the model double-check and retry its answer",
      patch: { enable_self_reflective: true },
    });

  return out.slice(0, 3);
}

// Merge the patches of the shown suggestions back onto the flags they came from.
export function applySuggestions(flags: QueryFlags, suggestions: Suggestion[]): QueryFlags {
  return suggestions.reduce((acc, s) => ({ ...acc, ...s.patch }), { ...flags });
}
