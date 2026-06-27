// These types mirror the Pydantic models in app/models.py. Keep them in sync with the
// backend — or, later, generate this file from the FastAPI /openapi.json (openapi-typescript).

export type SearchMode = "dense" | "sparse" | "hybrid";

export interface QueryRequest {
  question: string;
  top_k: number;
  enable_hyde: boolean;
  search_mode: SearchMode;
  enable_rerank: boolean | null;
  enable_crag: boolean;
  enable_self_reflective: boolean;
}

export interface RetrievedChunkPreview {
  text: string;
  source: string;
  score: number;
}

export interface ResponseMetadata {
  route: string;
  retrieved_chunks: RetrievedChunkPreview[];
  cache_hit: boolean;
  crag_triggered: boolean;
  crag_relevance_score: number | null;
  reflection_iterations: number;
  reflection_score: number | null;
  refined_question: string | null;
  executed_sql: string | null;
}

export interface PendingSQLBlock {
  sql: string;
  query_id: string;
  explanation: string;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
  confidence: number;
  pending_sql: PendingSQLBlock | null;
  cache_hit: boolean;
  cost_saved: string;
  metadata: ResponseMetadata;
}

export interface SQLApprovalRequest {
  query_id: string;
  approved: boolean;
}

export interface AuthResponse {
  token: string;
}
