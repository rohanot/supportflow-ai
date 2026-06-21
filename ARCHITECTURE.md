# Architecture

## Request Flow

```text
Streamlit UI
  -> FastAPI
  -> LangGraph chat workflow
  -> Hybrid retrieval / structured tools / HITL
  -> Postgres + pgvector + trace tables
```

## Core Boundaries

- `app/graph/` decides route, clarification, and handoff.
- `app/rag/` handles dense retrieval, lexical search, RRF fusion, and citations.
- `app/tools/` owns structured tool schemas and adapters.
- `app/api/v1/` exposes thin HTTP routes only.
- `app/observability/` redacts and supports trace rendering.
- `app/evals/` runs the offline scenario harness.

## Retrieval

- Dense retrieval uses FastEmbed query embeddings against `chunks.embedding` with HNSW ANN.
- Lexical retrieval uses Postgres full-text search on `chunks.search_vector`.
- Fusion uses Reciprocal Rank Fusion.
- `eval_data` and `test_data` are excluded from default retrieval.

## Service Area

- ZIP eligibility is structured lookup only.
- The assistant does not use vector search to decide whether a ZIP is serviceable.
- Retrieval may explain the policy after the structured result is known.

## Booking and HITL

- Booking create/reschedule/cancel are write actions that require explicit confirmation.
- Pending write actions are stored as HITL requests.
- Approval executes the stored payload through the matching tool adapter and writes a trace event.

## Tracing

- Every request gets a `trace_id`.
- Chat, clarification, retrieval, graph, tool, HITL, and prompt activity are persisted in local Postgres.
- Trace APIs expose the raw workflow for review through the backend and Streamlit.
