import type { ChatResponse, SearchMode } from "@/api/types";

// The query flags the user can toggle from the composer. Mirrors the optional fields of
// QueryRequest; `question` is supplied separately at send time.
export interface QueryFlags {
  top_k: number;
  search_mode: SearchMode;
  enable_hyde: boolean;
  enable_rerank: boolean | null;
  enable_crag: boolean;
  enable_self_reflective: boolean;
}

export const DEFAULT_FLAGS: QueryFlags = {
  top_k: 5,
  search_mode: "hybrid",
  enable_hyde: false,
  enable_rerank: true,
  enable_crag: true,
  enable_self_reflective: false,
};

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  question: string;
  // The pipeline flags this answer was produced with — used to suggest improvements
  // and to re-run the question with adjusted settings.
  flags: QueryFlags;
  // null while the request is in flight; populated once the backend responds.
  response: ChatResponse | null;
  error?: string;
  // streaming UI state, populated as SSE events arrive (cleared once `response` is set):
  stage?: string | null; // current pipeline stage label (routing/retrieving/grading/generating)
  streamedText?: string; // answer text accumulated token-by-token during generation
}

export type ChatMessage = UserMessage | AssistantMessage;
