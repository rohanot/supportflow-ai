# AGENTS.md

## Project

This repository contains ServiceFlow AI, configured for the Meridian Home Services case study.

The source of truth is `PRD_BRD.md`. Always read it before implementing a phase.

## Working Rules

* Build phase by phase.
* Do not attempt the entire project in one run.
* After each phase, stop and summarize:

  * files changed
  * commands run
  * tests run
  * what works
  * what is pending
* Prefer small, reviewable commits/diffs.
* Do not add dependencies without explaining why.
* Keep runtime lightweight.
* Do not install:

  * sentence-transformers
  * torch
  * promptfoo in runtime
  * ragas in runtime
  * crewai
  * agentscope
  * mem0ai
* Use FastEmbed + ONNX for dense retrieval.
* Use Postgres + pgvector for vector storage.
* Use Postgres full-text/BM25 for lexical retrieval.
* Use RRF for fusion.
* Use structured lookup for service-area eligibility.
* Do not use RAG for exact ZIP/service eligibility.
* All prompts must live under `/prompts`.
* No hardcoded prompts inside graph nodes, routes, or tool adapters.
* Every request must have a trace_id.
* Every graph node, prompt render, retrieval call, LLM call, clarification step, state transition, and tool call must be traceable.
* Use Pydantic validation before all tool calls.
* No write action may execute without explicit confirmation.

## Development Style

* Prefer simple code over clever abstractions.
* Implement only what the PRD requires for V1.
* Avoid overengineering.
* Keep Streamlit simple.
* Keep business logic out of Streamlit.
* Use FastAPI routes to call backend functionality.
* Add tests for every phase.
* When something fails, debug the smallest failing unit first.

## Required Phase Discipline

For every phase:

1. Read the relevant section of `PRD_BRD.md`.
2. Inspect the current repo state.
3. Make a short implementation plan.
4. Implement only that phase.
5. Run a consolidated test suite at the end of the phase covering all functionality implemented in that phase, including integration testing with previously completed phases where applicable.
6. Fix failures.
7. Stop and provide a summary.

Complete 5 stages at once then review checkpoint.
