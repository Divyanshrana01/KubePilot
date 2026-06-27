# KubePilot Frontend

React + TypeScript + Vite + Tailwind SPA for the Enterprise RAG / Kubernetes SRE Copilot.

## Features

- JWT auth (login / register) against the FastAPI backend
- Chat interface with markdown answers
- **Pipeline trace panel** — surfaces the backend's `ResponseMetadata`: route, CRAG
  trigger + relevance score, Self-RAG reflection iterations/score, retrieved chunks,
  cache hit, cost saved, and sources
- **SQL human-in-the-loop** — renders generated SQL with Approve / Reject, resuming the
  paused LangGraph run
- Per-request pipeline flags (search mode, top_k, HyDE, rerank, CRAG, Self-RAG)

## Run

The backend must be running on `http://localhost:8000` (override with `VITE_API_TARGET`).
Its CORS config already allowlists `http://localhost:5173`.

```bash
npm install
npm run dev          # http://localhost:5173
```

`/api/*` is proxied to the backend by Vite (see `vite.config.ts`), so the app talks to a
same-origin `/api` prefix in both dev and prod.

## Scripts

- `npm run dev` — dev server with HMR
- `npm run build` — typecheck + production build to `dist/`
- `npm run typecheck` — types only
- `npm run preview` — serve the production build

## Notes

- API types in `src/api/types.ts` mirror `app/models.py`. Once the backend adds streaming,
  swap the `api.query` call for an SSE reader; the trace panel is already shaped to render
  incrementally.
- Auth token is stored in `localStorage`. For production, consider an httpOnly cookie flow.
