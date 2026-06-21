# Path To Production

This repo is intentionally V1-shaped, not enterprise-complete.

## Current Production-Ready Core

- Dockerized FastAPI, Streamlit, Postgres, and LiteLLM
- FastEmbed + ONNX dense retrieval
- Postgres full-text lexical retrieval
- RRF fusion
- Structured service-area lookup
- Confirmation-gated write tools
- Local trace tables

## Next Steps For 11 Branches / ~8,500 Monthly Interactions

1. Move Postgres to managed Postgres with backups and retention.
2. Add auth and RBAC for branch-level visibility.
3. Add approval workflow for document and prompt changes.
4. Add scheduled eval runs and regression alerts.
5. Add rate limiting and abuse controls.
6. Add PII redaction policy for persisted customer content.
7. Add CRM or ticketing integration for handoff.
8. Add deployment pipeline and environment promotion.
9. Add optional Langfuse Cloud if the organization wants external observability.

## Hardening Plan

- Reliability: run API and Streamlit behind a reverse proxy, add health/readiness probes, database migrations in deployment, and alerting on failed ingestion, failed LLM calls, and failed tool calls.
- Data governance: add document ownership, upload approval, retention policy, customer PII minimization, and branch-scoped access rules.
- Retrieval quality: add scheduled golden-set evals, branch-specific regression suites, drift checks after every document upload, and manual approval for policy-changing documents.
- LLM operations: monitor latency, token usage, provider errors, fallback-provider rate, refusal/handoff rate, and answer-without-citation attempts.
- Tool safety: add audit logs for enable/disable changes, role-based approval for write tools, and separate permissions for create, reschedule, and cancel.
- Scale: 8,500 monthly interactions is modest; the likely bottlenecks are LLM provider latency and operator process quality, not Postgres throughput.

## Metrics To Monitor

- Retrieval hit rate and citation presence rate
- Low-confidence and handoff rate by branch/service
- Booking conversion rate after confirmation
- HITL approval/rejection volume
- Tool error rate and disabled-tool attempts
- LLM latency, provider failures, and retry count
- Ingestion chunk count, embedding count, and eval-data exclusion checks

## Branch-Specific Policy Rollout

1. Tag every document and chunk with branch, region, service, effective date, and doc type.
2. Require metadata filters for branch-specific answers when branch or ZIP is known.
3. Ask clarification when the branch/region is required but missing.
4. Keep structured tables separate from RAG for exact eligibility and operational decisions.
5. Run branch-specific evals before promoting new policy documents.

## What Should Not Change

- The LangGraph / workflow shape
- The tool adapter boundaries
- The prompt registry layout
- The retrieval abstraction
- The structured service-area lookup path

Those are the seams that should survive production hardening.
