# Eval Results

Generated: 2026-06-21T14:36:00+00:00
- eval_name: serviceflow_scenario_v1
- total_cases: 11
- passed_cases: 11
- failed_cases: 0
- metrics:
  - scenario_pass_rate: 1.0
  - retrieval_hit_rate: 1.0
  - citation_presence_rate: 1.0
  - confirmation_gate_rate: 1.0
  - prompt_injection_guard_rate: 1.0
  - eval_data_exclusion_rate: 1.0
- embedding_backend: fastembed
- embedding_model: BAAI/bge-small-en-v1.5
- embedding_dimension: 384
- hnsw_status: available
- gin_status: available
- eval_data_excluded: true

Scenario coverage:
- pricing_clarification
- pricing_followup
- service_area_clarification
- service_area_followup
- emergency_handoff
- no_show_fee_retrieval
- herndon_hours_retrieval
- booking_confirmation_gate
- approved_hitl_booking
- prompt_injection_guard
- eval_data_exclusion
