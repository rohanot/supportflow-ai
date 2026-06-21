# Prompt Audit

## Folder Layout

- `prompts/registry.yaml` is the source of truth.
- Prompt files are YAML and live under `prompts/`.
- The prompt manager loads, validates, and renders them.

## What Gets Traced

- prompt name
- prompt version
- prompt hash
- redacted prompt inputs
- rendered preview

## How To Inspect

- `GET /api/v1/prompts`
- `GET /api/v1/traces/{trace_id}/prompts`
- Streamlit `9_Prompt_Audit.py`

## Rules

- No hardcoded prompts inside routes, graph nodes, or adapters.
- Prompt edits should happen through code changes so they remain Git-auditable.
- Prompt traces should never store full sensitive customer content.
