# Guardrails

## Required

- Every request gets a `trace_id`.
- Every prompt lives under `prompts/`.
- Every write action requires explicit confirmation.
- Service-area eligibility is structured lookup only.
- `eval_data` and `test_data` are excluded from default retrieval.
- FastEmbed + ONNX are the runtime embedding path.
- If FastEmbed is unavailable in runtime, the app fails loudly unless fallback is explicitly enabled.

## Forbidden In V1

- `sentence-transformers`
- `torch`
- runtime `promptfoo`
- runtime `ragas`
- CrewAI
- AgentScope
- Mem0
- custom React frontend
- self-hosted Langfuse stack
- RAG for exact ZIP eligibility

## Operational Rules

- Keep Streamlit thin.
- Keep business logic in backend modules.
- Keep prompts auditable and versioned.
- Keep tool adapters deterministic.
- Keep approval and rejection traceable.
