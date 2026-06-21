# Debugging Methodology

## First Moves

- Check `trace_id`.
- Reproduce the smallest failing request.
- Inspect the trace detail endpoint.
- Check graph, retrieval, clarification, and tool sub-views.
- Prefer the smallest failing unit over broad guessing.

## Trace-First Workflow

1. `GET /api/v1/traces`
2. `GET /api/v1/traces/{trace_id}`
3. Inspect `/graph`, `/retrieval`, `/tools`, `/clarification`
4. Compare the stored state to the expected route

## Common Failure Modes

- Missing clarification slot
- Unsafe write action without confirmation
- Retrieval hitting the wrong document type
- `eval_data` leaking into customer retrieval
- Stale Docker image or stale container

## Local Notes

- On Codex desktop, `git status` may fail if the workspace is not exposed as a valid git repository.
- That does not mean the files are missing.
- Use file inspection and runtime checks when git is unavailable.

## Redaction

- Trace endpoints redact sensitive text fields.
- Use the backend trace views instead of printing raw state dumps.
