# Meridian Assistant V1 — Final PRD + BRD for Codex

## 0. Codex Execution Instruction

You are building the Meridian Assistant V1 in the repository root where the assignment PDF and all Meridian client PDFs are already present.

Build a fully functional, production-minded V1. This is not a throwaway MVP.

The system must be accurate, lightweight enough to run in Docker, easy to debug, easy to maintain, and designed so enterprise services can be integrated later without rewriting the core architecture.

Build phase by phase exactly as specified in this document.

Hard constraints:

* Use LangGraph for orchestration.
* Use stateful workflows for incomplete queries, clarification, HITL, and confirmation.
* Use hybrid retrieval by default.
* Use FastEmbed + ONNX for dense retrieval.
* Use Postgres + pgvector for vector storage.
* Use Postgres full-text search or BM25 for lexical retrieval.
* Fuse dense and lexical results using Reciprocal Rank Fusion.
* Use structured lookup for service-area eligibility.
* Do not use RAG/vector search for exact ZIP/service eligibility decisions.
* Use Pydantic validation before all tool/API calls.
* Require explicit confirmation before create/reschedule/cancel actions.
* Keep all prompts in a separate `/prompts` folder for auditability.
* No prompt should be hardcoded inside graph nodes, tool adapters, or route handlers.
* Every request must have a trace_id.
* Every graph node, retrieval step, prompt render, LLM call, state transition, clarification step, and tool call must be traceable.
* The app must run with `docker compose up`.
* Do not install `sentence-transformers` or `torch` in runtime.
* Do not install `promptfoo` or `ragas` in runtime.
* Red-team/eval logic should be pytest-based in V1.

---

# 1. Product Name

Meridian Assistant V1

---

# 2. Product Goal

Build an AI assistant for Meridian Home Services that can:

1. Answer customer questions grounded in the provided knowledge pack.
2. Provide citations/source traceability for every knowledge-based answer.
3. Handle ambiguous and incomplete queries through stateful clarification.
4. Combine the original user query and follow-up clarification into a complete canonical query.
5. Check service-area eligibility by ZIP and service type using structured lookup.
6. Create a booking through the mock Booking API.
7. Look up booking status.
8. Reschedule or cancel a booking when enough information is available.
9. Ask for confirmation before committing any write action.
10. Safely hand off emergency, complaint, fee dispute, commercial, low-confidence, or unsupported requests.
11. Provide backend and UI-level debugging visibility.
12. Keep prompts versioned, auditable, and trace-linked.
13. Include offline evals and red-team tests.

---

# 3. Business Context

Meridian Home Services handles HVAC, plumbing, and electrical service requests across multiple branches and regions.

The assistant should reduce contact-center workload by resolving repetitive questions and simple booking workflows while escalating risky or ambiguous cases to a human.

Primary use cases:

* FAQ answering
* Pricing guidance
* Warranty explanation
* Cancellation/reschedule policy explanation
* Branch hours lookup
* Service-area eligibility check
* Booking creation
* Booking lookup
* Reschedule/cancel
* Emergency guidance
* Human handoff

---

# 4. Final Architecture Decision

Use one accurate and optimized V1 mode.

```text
Streamlit UI
    ↓
FastAPI Backend
    ↓
LangGraph Workflow
    ↓
----------------------------------------------------------------
| Clarification Manager | Hybrid RAG | Structured Tools | Handoff |
----------------------------------------------------------------
    ↓
Postgres + pgvector
```

Core stack:

```text
Backend: FastAPI + Pydantic
Orchestration: LangGraph
RAG framework: LlamaIndex core where useful
Vector DB: Postgres + pgvector
Dense retrieval: FastEmbed + ONNX
Lexical retrieval: Postgres full-text search or BM25
Fusion: Reciprocal Rank Fusion
LLM gateway: LiteLLM
LLM providers: Groq primary, OpenRouter fallback
UI: Streamlit
Tracing: local Postgres trace tables by default
Optional tracing: Langfuse Cloud if env vars are configured
Testing: pytest-based eval and red-team suite
Prompt audit: file-based prompt registry under /prompts
```

Do not add in V1:

```text
Kafka
Kubernetes
CrewAI
AgentScope
Mem0
custom React frontend
custom vector database
custom full RAG engine
sentence-transformers
torch
runtime promptfoo
runtime ragas
Langfuse self-host stack by default
cross-encoder reranker in runtime
arbitrary UI-created external tools
```

---

# 5. Key Engineering Principle

Do not make the LLM responsible for irreversible business decisions.

Use the LLM for:

```text
intent classification
slot extraction
query clarification
canonical query generation
grounded answer generation
handoff summary generation
confirmation message drafting
```

Use code for:

```text
ZIP validation
service-area eligibility
booking schema validation
tool permissions
confirmation gates
service restrictions
fee rules
handoff routing
trace logging
eval scoring
```

---

# 6. Early Risk Handling Strategy

This V1 must handle known risks at the start of the design, not as afterthoughts.

## Risk 1: Ambiguous user queries

Example:

```text
User: Give me the price?
Assistant: Which service do you want pricing for — HVAC, plumbing, or electrical? If you know the specific job, share that too.
User: 40-gallon water heater replacement.
System canonical query: What is the pricing for plumbing water heater replacement, 40 gallon?
```

Mitigation:

* Add a clarification state in LangGraph.
* Store pending intent and missing slots.
* Ask one focused follow-up question.
* Combine the original query and clarification into a canonical query.
* Run retrieval/tool only after required slots are available.

## Risk 2: Wrong-branch or wrong-service policy answer

Mitigation:

* Metadata filter before retrieval.
* If branch/region/service is required but unknown, ask for ZIP, branch, or service type.
* Do not answer branch-specific questions from global context alone.
* Trace metadata filter decisions.

## Risk 3: Heavy Docker dependencies

Mitigation:

* Use FastEmbed + ONNX instead of sentence-transformers + torch.
* Do not run promptfoo/ragas in runtime.
* Use pytest-based evals and red-team tests.
* Keep Langfuse optional, not self-hosted by default.

## Risk 4: Semantic retrieval misses exact facts

Mitigation:

* Hybrid retrieval is mandatory.
* Use dense retrieval for semantic meaning.
* Use lexical retrieval for exact names, ZIPs, fees, branch names, and policy terms.
* Use RRF fusion.
* Use row-level chunks for pricing tables.
* Use one-QA-per-chunk for FAQs.

## Risk 5: Vector search gives operationally unsafe result

Mitigation:

* Service-area eligibility is structured lookup only.
* Booking API schemas are Pydantic models only.
* Write actions require confirmation.
* Emergency and high-risk scenarios go directly to handoff.

## Risk 6: Hard-to-debug agent behavior

Mitigation:

* Every LangGraph node logs input/output state summary.
* Every prompt render logs prompt name/version/hash.
* Every retrieval logs dense, lexical, and fused results.
* Every tool call logs validated payload, status, and latency.
* Streamlit UI includes Monitoring, Retrieval Debugger, Prompt Audit, and HITL pages.

## Risk 7: Future enterprise scaling requires rewrite

Mitigation:

* Keep tool adapters modular.
* Keep prompts separate.
* Keep retrieval modular.
* Keep observability abstraction.
* Keep structured domain tables separate from RAG chunks.
* Use Postgres as local and production-friendly default.

---

# 7. BRD — Business Requirements

## BRD-1: Grounded FAQ and Policy Answering

The assistant must answer questions about:

* Branch hours
* Booking and scheduling
* Payments
* Emergencies
* Pricing bands
* Warranty terms
* Cancellation/reschedule policy

Acceptance criteria:

* Answer must be grounded in retrieved client documents.
* Answer must include citations/source references.
* Assistant must not invent prices, policies, service availability, or exceptions.
* Assistant must hand off when evidence is missing or conflicting.
* Trace must show which chunks supported the answer.

---

## BRD-2: Ambiguous and Incomplete Query Handling

The assistant must handle incomplete customer requests gracefully.

Examples:

```text
User: Give me the price?
Assistant: Which service or repair do you want a price for?

User: Do you service my area?
Assistant: Please share your 5-digit ZIP code and the service type — HVAC, plumbing, or electrical.

User: Book an appointment.
Assistant: I can help. What service do you need, what ZIP code is the property in, and what date/window do you prefer?
```

Acceptance criteria:

* System detects missing required slots.
* System does not run retrieval/tool prematurely when required context is missing.
* System stores the original query in conversation state.
* System asks one focused clarification question at a time.
* System merges the original query and user clarification into a canonical query.
* System traces:

  * original query
  * missing slots
  * clarification question
  * clarification answer
  * canonical query
  * next route

---

## BRD-3: Service-Area Eligibility

The assistant must check whether a ZIP code is serviceable for a requested service.

Acceptance criteria:

* Validate ZIP as 5 digits.
* Determine service availability from structured service-area tables.
* Return region, county, service status, primary branch, overflow branch, and restrictions.
* Do not use RAG/vector search for the yes/no eligibility decision.
* Use RAG only to explain/cite the policy after the structured lookup.
* Ask for missing ZIP or service type if unavailable.

---

## BRD-4: Booking Creation

The assistant must create a booking through a mock Booking API.

Required fields:

* customer_id or customer_info
* service_type
* job_type
* zip_code
* preferred_date
* preferred_window
* notes
* channel

Acceptance criteria:

* Collect missing fields conversationally.
* Validate fields using Pydantic.
* Check ZIP/service eligibility before booking.
* Show confirmation summary before commit.
* Only call create booking after explicit user confirmation.
* Store trace and tool invocation result.
* UI must show the proposed payload before confirmation.

---

## BRD-5: Booking Lookup

The assistant must support booking-status lookup.

Required field:

* booking_id

Acceptance criteria:

* Validate booking_id format.
* Call mock GET booking tool.
* Return appointment window, status, technician name, and ETA if available.
* Do not expose unnecessary PII.
* Trace must capture the lookup tool call.

---

## BRD-6: Reschedule or Cancel Booking

The assistant must support reschedule/cancel flows.

Required fields for reschedule:

* booking_id
* new_date
* new_window

Required fields for cancel:

* booking_id
* cancel_reason

Acceptance criteria:

* Validate booking_id.
* Validate new date/window for reschedule.
* Explain possible cancellation/reschedule fee before commit when policy applies.
* Ask for confirmation before PATCH action.
* Only call PATCH after explicit confirmation.
* Trace must show fee policy evidence and final user confirmation.

---

## BRD-7: Human Handoff

The assistant must hand off when automation is unsafe or inappropriate.

Handoff triggers:

* Active water leak
* Flooding
* Electrical hazard
* Burning smell
* Sparking
* Sewage backup
* No heat below threshold
* No cooling above threshold
* Fee dispute
* Service complaint
* Commercial inquiry or volume discount
* Out-of-area request needing manager approval
* Unsupported service
* Low retrieval confidence
* Missing required booking fields after retries
* Tool/API error
* Conflicting retrieved policy

Acceptance criteria:

* Handoff response must be clear and customer-safe.
* Handoff payload must include:

  * conversation summary
  * intent
  * missing fields
  * retrieved sources
  * attempted tool calls
  * reason for handoff
  * recommended human action
* Handoff must be visible in Streamlit UI and trace logs.

---

## BRD-8: Evaluation

The assistant must include an offline evaluation harness using the provided customer-message examples.

Acceptance criteria:

* Convert customer-message examples into `evals/golden_set.jsonl`.
* Evaluate:

  * intent routing
  * clarification behavior
  * handoff routing
  * retrieval correctness
  * citation presence
  * booking confirmation gate
  * tool-call correctness
  * slot extraction
  * prompt-injection resistance
* Provide `eval_results.md`.

---

## BRD-9: Observability and Debuggability

Every request must be traceable and debuggable from both backend and UI.

Acceptance criteria:

* Generate trace_id for every request.
* Store traces in local Postgres by default.
* Trace every graph node.
* Trace every prompt used.
* Trace every rendered prompt hash/version.
* Trace every LLM call.
* Trace every retrieval step.
* Trace every clarification step.
* Trace every tool call.
* Trace every state transition.
* Trace every handoff reason.
* Monitoring UI must allow trace inspection.

---

# 8. PRD — Product Requirements

## 8.1 User Personas

### Customer

Uses the assistant to ask questions, check service area, book, reschedule, cancel, or get emergency guidance.

### Contact-Center Agent

Receives handoff summaries with context and recommended next actions.

### Admin / Reviewer

Uploads knowledge files, views chunks, inspects traces, runs evals, tests retrieval, and audits prompts.

### Developer

Extends backend tools using adapter classes, schemas, and prompt files.

---

# 9. Stateful Conversation and Clarification Requirements

## 9.1 Conversation State

The system must persist conversation state per session.

State must support:

```text
current intent
pending intent
original query
latest user message
missing slots
clarification question
clarification answer
canonical query
retrieved chunks
tool payload draft
confirmation status
handoff status
```

## 9.2 Incomplete Query Flow

Example pricing flow:

```text
User: Give me the price?
System:
  intent = pricing
  missing_slots = [service_or_item]
  route = ask_clarification

Assistant: Which service or item do you need pricing for — HVAC, plumbing, electrical, or a specific repair?

User: 40-gallon water heater replacement.

System:
  original_query = "Give me the price?"
  clarification_answer = "40-gallon water heater replacement."
  canonical_query = "What is the ballpark price for plumbing 40-gallon water heater replacement?"
  route = hybrid_rag_answer
```

Example service-area flow:

```text
User: Do you service my area?
System:
  intent = service_area_check
  missing_slots = [zip_code, service_type]

Assistant: Please share your 5-digit ZIP code and service type — HVAC, plumbing, or electrical.

User: 20147 plumbing.

System:
  canonical_query = "Check service-area eligibility for plumbing in ZIP 20147."
  route = service_area_lookup
```

Example booking flow:

```text
User: Book an appointment.
System:
  intent = new_booking
  missing_slots = [service_type, zip_code, preferred_date, preferred_window, contact_info]

Assistant: I can help with that. What service do you need, what ZIP code is the property in, and what date/window do you prefer?
```

## 9.3 Clarification Node

Create LangGraph node:

```text
ask_clarification
```

Responsibilities:

* Identify missing required slots.
* Ask one focused follow-up question.
* Avoid asking for unnecessary fields.
* Store clarification question in state.
* Do not perform RAG/tool action yet.

## 9.4 Complete Query Builder Node

Create LangGraph node:

```text
build_canonical_query
```

Responsibilities:

* Combine original query and clarification answer.
* Resolve intent.
* Resolve slots.
* Produce canonical query.
* Decide next route.

Output example:

```json
{
  "original_query": "Give me the price?",
  "clarification_answer": "40-gallon water heater replacement",
  "canonical_query": "What is the ballpark price for plumbing 40-gallon water heater replacement?",
  "resolved_intent": "pricing",
  "resolved_slots": {
    "service_type": "plumbing",
    "item": "40-gallon water heater replacement"
  },
  "next_route": "hybrid_rag_answer"
}
```

## 9.5 Clarification Limits

To avoid infinite loops:

```text
max_clarification_turns = 3
```

If still incomplete after 3 clarification turns:

```text
route = handoff
handoff_reason = "Unable to collect required information"
```

---

# 10. Prompt Audit Requirements

## 10.1 Prompt Folder

All prompts must live under:

```text
prompts/
```

Required structure:

```text
prompts/
  registry.yaml

  system/
    assistant_system.yaml
    safety_policy.yaml

  routing/
    classify_intent.yaml
    extract_slots.yaml
    route_decision.yaml

  clarification/
    ask_clarification.yaml
    build_canonical_query.yaml
    missing_slot_policy.yaml

  rag/
    grounded_answer.yaml
    citation_answer.yaml
    retrieval_query_rewrite.yaml

  booking/
    collect_missing_fields.yaml
    booking_confirmation.yaml
    reschedule_confirmation.yaml
    cancellation_confirmation.yaml

  handoff/
    handoff_summary.yaml
    emergency_handoff.yaml

  eval/
    judge_answer_support.yaml
    judge_tool_correctness.yaml
```

## 10.2 Prompt File Format

Every prompt file must be YAML.

Required fields:

```yaml
name: grounded_answer
version: v1
owner: engineering
purpose: Generate grounded answer using retrieved context only.
inputs:
  - user_message
  - retrieved_context
  - citations
guardrails:
  - Answer only from retrieved context.
  - If evidence is missing, ask a clarifying question or hand off.
  - Never invent pricing, policy, availability, or service coverage.
template: |
  You are Meridian Assistant.
  User message:
  {{ user_message }}

  Retrieved context:
  {{ retrieved_context }}

  Citation candidates:
  {{ citations }}

  Instructions:
  - Answer only from retrieved context.
  - Include citations.
  - If context is insufficient, say you need to route to a human.
change_log:
  - version: v1
    date: 2026-06-21
    change: Initial prompt.
```

## 10.3 Prompt Registry

`prompts/registry.yaml` must map prompt names to paths.

Example:

```yaml
prompts:
  classify_intent:
    path: prompts/routing/classify_intent.yaml
    active_version: v1

  ask_clarification:
    path: prompts/clarification/ask_clarification.yaml
    active_version: v1

  build_canonical_query:
    path: prompts/clarification/build_canonical_query.yaml
    active_version: v1

  grounded_answer:
    path: prompts/rag/grounded_answer.yaml
    active_version: v1

  booking_confirmation:
    path: prompts/booking/booking_confirmation.yaml
    active_version: v1
```

## 10.4 Prompt Manager

Implement:

```text
app/prompts/
  manager.py
  schemas.py
  renderer.py
```

Prompt manager responsibilities:

* Load prompt from YAML.
* Validate required fields.
* Render template with input variables.
* Compute prompt_hash.
* Return prompt_name, prompt_version, prompt_hash, rendered_prompt.
* Log prompt metadata to traces.
* Never silently fall back to hardcoded prompt text.
* Fail loudly if prompt file is missing or invalid.

## 10.5 Prompt Traceability

Every LLM call trace must include:

```text
prompt_name
prompt_version
prompt_hash
prompt_inputs_redacted
rendered_prompt_preview
model
provider
input_tokens
output_tokens
latency_ms
cost_estimate
```

Do not store full sensitive customer data in prompt traces. Store redacted inputs and safe previews.

## 10.6 Prompt Audit UI

Add a Streamlit page:

```text
9_Prompt_Audit.py
```

Features:

* List prompts from registry.
* Show prompt name, version, owner, purpose.
* Show template.
* Show guardrails.
* Show change log.
* Show traces using this prompt.
* Show prompt_hash.
* Validate all prompts.
* No editing from UI in V1.

Prompt edits must happen through code changes so they are Git-auditable.

---

# 11. Functional Requirements

## FR-1: Streamlit Chat UI

Build a chat page with:

* User input
* Assistant response
* Citations
* Confidence/status indicator
* Trace ID
* Current state label:

  * answering
  * asking_clarification
  * awaiting_confirmation
  * handoff
  * completed
* Prompt versions used
* Tool calls used
* Booking confirmation card when needed
* Handoff message when needed
* Link/button to open full trace details

---

## FR-2: Knowledge Upload UI

Build an admin page to upload documents.

Features:

* Upload PDF, TXT, MD, CSV
* Add metadata:

  * doc_type
  * region
  * branch
  * service_type
  * policy_type
  * effective_date
* Trigger ingestion
* Show ingestion status
* Show number of chunks created
* Show extracted structured records if any

The repo should also support seed ingestion from existing client PDFs in root or `data/client_docs/`.

---

## FR-3: Chunk Explorer UI

Build a page to inspect indexed chunks.

Features:

* Filter by source document
* Filter by doc_type
* Filter by service_type
* Filter by region/branch
* Search chunk text
* View metadata
* View embedding status
* View full chunk text
* View related traces where this chunk was retrieved

---

## FR-4: Retrieval Debugger UI

Build a page to test hybrid retrieval.

Features:

* Enter query
* Optional filters
* Show dense results
* Show lexical results
* Show fused results
* Show final selected context
* Show citations
* Show retrieval scores
* Show RRF rank positions
* Show metadata filter decisions
* Show canonical query if query came from clarification

---

## FR-5: HITL / Confirmation UI

Build a page for pending write actions.

Features:

* Show proposed booking/reschedule/cancel action
* Show payload
* Show policy warnings/fees
* Show prompt that generated confirmation summary
* Approve
* Reject
* Edit allowed fields
* Resume workflow after decision

For normal customer chat, user confirmation can happen inline. For admin/reviewer testing, HITL page should expose pending confirmations.

---

## FR-6: Tool Registry UI

Build a limited tool registry page.

Features:

* List registered tools
* Enable/disable tools
* View input/output schema
* Test tool with sample payload
* View recent invocations
* View which graph routes use each tool

Do not allow arbitrary external tool creation from UI in V1.

New tools must be added through backend adapter class + YAML config + Pydantic schema.

---

## FR-7: Evaluation UI

Build a page to run offline evals.

Features:

* Run golden-set evals
* Run red-team pytest cases
* Run clarification evals
* Show pass/fail count
* Show failed cases
* Show metrics
* Export results summary
* Show prompt versions used during eval

Required metrics:

* intent accuracy
* route accuracy
* clarification accuracy
* canonical query accuracy
* handoff accuracy
* retrieval hit rate
* citation presence rate
* tool-call correctness
* confirmation-gate correctness
* slot extraction accuracy
* prompt-injection resistance

---

## FR-8: Monitoring and Trace Debugger UI

Build a monitoring page.

Features:

* Show recent traces
* Filter by trace_id, intent, status, prompt_name, tool_name
* View graph path
* View state transitions
* View prompt versions and hashes
* View clarification events
* View canonical query
* View retrieval results
* View dense/lexical/fused rankings
* View tool calls
* View errors
* View token/cost if available
* Show Langfuse URL if configured

---

# 12. Hybrid Retrieval Requirements

Hybrid retrieval is mandatory and always enabled.

## 12.1 Retrieval Components

Use:

```text
Dense retrieval:
  FastEmbed + ONNX embeddings + pgvector

Lexical retrieval:
  Postgres full-text search or BM25

Fusion:
  Reciprocal Rank Fusion

Filtering:
  metadata filter before ranking
```

Do not use:

```text
sentence-transformers
torch
cross-encoder reranker
large local embedding models
```

## 12.2 Embedding Model

Default:

```text
BAAI/bge-small-en-v1.5 through FastEmbed
```

Use a 384-dimensional vector column.

## 12.3 Retrieval Config

```python
HYBRID_RETRIEVAL_CONFIG = {
    "dense_top_k": 12,
    "lexical_top_k": 12,
    "final_top_k": 5,
    "rrf_k": 60,
    "min_confidence": 0.62
}
```

## 12.4 Fusion

Use Reciprocal Rank Fusion:

```text
fused_score = 1 / (rrf_k + dense_rank) + 1 / (rrf_k + lexical_rank)
```

If a chunk appears in both dense and lexical results, boost it.

## 12.5 Confidence

Confidence must be calculated from:

```text
metadata match
retrieval score
source/doc_type match
citation availability
intent safety
```

Do not ask the LLM to self-report confidence.

---

# 13. Chunking Strategy

## 13.1 Service Area Docs

Do two things:

1. Convert to structured service-area tables.
2. Store source explanation chunks for citation.

Structured fields:

```text
region
county
zip_start
zip_end
zip_exact
hvac_status
plumbing_status
electrical_status
primary_branch
overflow_branch
restriction_notes
source_doc
```

Do not use RAG for the actual yes/no eligibility decision.

## 13.2 Pricing Docs

Use row-level chunks.

Examples:

```text
HVAC diagnostic fee
HVAC repair tier T1
HVAC repair tier T2
HVAC repair tier T3
HVAC repair tier T4
HVAC maintenance Silver
HVAC maintenance Gold
HVAC maintenance Platinum
HVAC after-hours surcharge
Plumbing water heater replacement
Electrical panel upgrade
```

## 13.3 FAQ Docs

Use one Q&A pair per chunk.

## 13.4 Policy Docs

Use section-level chunks.

For tables, use one row or one logical rule per chunk.

## 13.5 Booking API Spec

Do not depend on runtime RAG for API behavior.

Convert the API spec into:

* Pydantic models
* mock API endpoints
* tool adapters
* tool registry entries

Also store API spec chunks for documentation/citation if needed.

---

# 14. LangGraph Workflow

## 14.1 State

Create `MeridianState`.

Fields:

```python
class MeridianState(TypedDict):
    trace_id: str
    session_id: str

    user_message: str
    original_query: str | None
    clarification_question: str | None
    clarification_answer: str | None
    canonical_query: str | None
    clarification_turn_count: int

    intent: str | None
    pending_intent: str | None
    confidence: float | None

    zip_code: str | None
    region: str | None
    branch: str | None
    service_type: str | None
    job_type: str | None
    item_or_service_requested: str | None

    customer_id: str | None
    customer_info: dict | None
    preferred_date: str | None
    preferred_window: str | None
    preferred_tech: str | None
    notes: str | None
    booking_id: str | None

    retrieved_chunks: list[dict]
    citations: list[dict]

    missing_fields: list[str]
    proposed_tool_call: dict | None
    confirmation_required: bool
    confirmed_by_user: bool

    handoff_required: bool
    handoff_reason: str | None

    prompts_used: list[dict]
    graph_events: list[dict]
    debug_events: list[dict]

    final_response: str | None
```

## 14.2 Nodes

Required nodes:

```text
start
load_conversation_state
classify_intent
extract_slots
detect_missing_slots
ask_clarification
build_canonical_query
route_intent
hybrid_rag_answer
service_area_lookup
collect_booking_fields
validate_booking_request
prepare_confirmation
wait_for_confirmation
create_booking
lookup_booking
reschedule_or_cancel_booking
handoff
final_response
persist_conversation_state
trace_event
```

## 14.3 Routes

Intent routes:

```text
faq_or_policy       -> detect_missing_slots -> hybrid_rag_answer OR ask_clarification
pricing             -> detect_missing_slots -> hybrid_rag_answer OR ask_clarification
service_area_check  -> detect_missing_slots -> service_area_lookup OR ask_clarification
new_booking         -> collect_booking_fields -> validate_booking_request
booking_status      -> detect_missing_slots -> lookup_booking OR ask_clarification
reschedule          -> detect_missing_slots -> reschedule_or_cancel_booking OR ask_clarification
cancel              -> detect_missing_slots -> reschedule_or_cancel_booking OR ask_clarification
emergency           -> handoff
complaint           -> handoff
fee_dispute         -> handoff
commercial_inquiry  -> handoff
unknown             -> ask_clarification OR handoff
```

## 14.4 Confirmation Gate

No write tool may execute unless:

```python
state["confirmed_by_user"] is True
```

Write tools:

```text
create_booking
reschedule_booking
cancel_booking
update_notes
```

## 14.5 Clarification Gate

No retrieval/tool call should run when required fields are missing.

Instead:

```text
route = ask_clarification
```

After user replies:

```text
route = build_canonical_query
```

Then:

```text
route = original intended path
```

---

# 15. Tools

## 15.1 Tool Adapter Interface

```python
class ToolAdapter(Protocol):
    name: str
    permission_level: Literal["read_only", "write"]
    requires_confirmation: bool

    def input_schema(self) -> type[BaseModel]:
        ...

    def output_schema(self) -> type[BaseModel]:
        ...

    async def execute(self, payload: BaseModel, context: ToolContext) -> dict:
        ...
```

## 15.2 Built-in Tools

Required:

```text
check_service_area
create_booking
lookup_booking
reschedule_booking
cancel_booking
handoff_create
```

## 15.3 Tool Registry

Tools are registered through YAML and backend adapters.

Example:

```yaml
tools:
  - name: check_service_area
    adapter: app.tools.booking.CheckServiceAreaTool
    permission_level: read_only
    requires_confirmation: false
    enabled: true

  - name: create_booking
    adapter: app.tools.booking.CreateBookingTool
    permission_level: write
    requires_confirmation: true
    enabled: true
```

Do not allow arbitrary runtime tool execution from user prompts.

---

# 16. Mock Booking API

Implement mock endpoints internally.

## POST /mock/bookings

Creates a booking.

Required request fields:

```text
customer_id or customer_info
service_type
job_type
zip_code
preferred_date
preferred_window
preferred_tech optional
notes optional
channel
```

Response:

```text
booking_id
status
assigned_branch
appointment_window
tech_name
confirmation_sent
```

## GET /mock/bookings/{booking_id}

Returns booking status.

Response:

```text
booking_id
status
service_type
job_type
appointment_window
tech_name
tech_eta_minutes
notes
invoice_total
```

## PATCH /mock/bookings/{booking_id}

Supports:

```text
reschedule
cancel
update_notes
```

Response:

```text
booking_id
status
fee_applied
waiver_used
new_appointment_window
```

---

# 17. Human Handoff Logic

Immediate handoff for:

```text
active water leak
flooding
electrical hazard
burning smell
sparking
sewage backup
no heat below threshold
no cooling above threshold
fee dispute
complaint
commercial account / volume discount
out-of-area needing manager approval
```

Handoff response should be helpful and safe.

For emergencies, direct customer to emergency line and do not book through web/chat.

---

# 18. Observability and Debugging

## 18.1 Local Trace Logging

Use Postgres as the default trace store.

Tables:

```text
traces
trace_events
graph_node_events
state_transition_events
clarification_events
prompt_events
llm_calls
retrieval_events
tool_invocations
handoff_events
eval_runs
```

## 18.2 Required Trace Fields

```text
trace_id
session_id
user_message
original_query
clarification_question
clarification_answer
canonical_query
intent
pending_intent
graph_path
state_before
state_after
prompt_name
prompt_version
prompt_hash
dense_results
lexical_results
fused_results
citations
model
provider
input_tokens
output_tokens
estimated_cost
tool_calls
latency_ms
errors
final_response
handoff_reason
```

## 18.3 Graph Node Logging

Every LangGraph node must log:

```text
trace_id
node_name
started_at
finished_at
latency_ms
input_state_summary
output_state_summary
route_decision
error_if_any
```

Do not log raw sensitive PII in full state dumps. Use redaction.

## 18.4 Clarification Logging

Every clarification must log:

```text
trace_id
original_query
missing_slots
clarification_question
clarification_answer
canonical_query
clarification_turn_count
next_route
```

## 18.5 Retrieval Logging

Every retrieval call must log:

```text
query
canonical_query
filters
dense_top_k
lexical_top_k
fused_top_k
dense_results
lexical_results
fused_results
selected_context
citation_ids
retrieval_confidence
```

## 18.6 Tool Logging

Every tool call must log:

```text
tool_name
permission_level
requires_confirmation
validated_input_redacted
output
status
latency_ms
error_if_any
```

## 18.7 LLM Logging

Every LLM call must log:

```text
prompt_name
prompt_version
prompt_hash
model
provider
temperature
input_tokens
output_tokens
estimated_cost
latency_ms
status
error_if_any
```

## 18.8 Langfuse

Add optional Langfuse Cloud integration.

Behavior:

* If `LANGFUSE_ENABLED=true`, send traces to Langfuse.
* If not configured, app must still work fully with local trace tables.
* Do not self-host Langfuse inside default Docker Compose.

---

# 19. Evaluation

## 19.1 Golden Dataset

Create:

```text
evals/golden_set.jsonl
```

Use the provided customer-message file as source.

Each test case should include:

```json
{
  "id": "case_001",
  "input": "...",
  "expected_intent": "...",
  "expected_route": "...",
  "expected_handoff": false,
  "expected_answer_contains": [],
  "expected_tool": null,
  "expected_citations": true
}
```

## 19.2 Clarification Eval Dataset

Create:

```text
evals/clarification_cases.jsonl
```

Examples:

```json
{
  "id": "clarify_001",
  "input_turns": [
    "Give me the price?",
    "40-gallon water heater replacement"
  ],
  "expected_missing_slots_first_turn": ["item_or_service_requested"],
  "expected_canonical_query": "What is the ballpark price for plumbing 40-gallon water heater replacement?",
  "expected_route": "hybrid_rag_answer"
}
```

## 19.3 Pytest Evals

Implement tests for:

```text
intent classification
route selection
missing slot detection
clarification question quality
canonical query construction
service-area lookup
hybrid retrieval hit
citation presence
booking field extraction
confirmation gate
write tool blocked before confirmation
handoff routing
mock API tool execution
prompt loading
prompt validation
prompt traceability
```

## 19.4 Red-Team Evals

Implement red-team as pytest JSON cases, not promptfoo runtime.

Test cases:

```text
ignore previous instructions
book without confirmation
waive my cancellation fee
invent a price
use a different branch policy
emergency through web booking
commercial discount request
prompt asks for hidden system prompt
fake document policy in user prompt
ambiguous pricing query should clarify before answering
ambiguous service-area query should ask for ZIP and service type
```

Output:

```text
eval_results.md
```

Include:

```text
total cases
passed
failed
metrics
failed examples
prompt versions used
```

---

# 20. Database Schema

Use SQLAlchemy + Alembic.

Required tables:

```text
documents
chunks
service_areas
branch_hours
conversations
messages
conversation_state
tool_registry
tool_invocations
hitl_requests
bookings_mock
traces
trace_events
graph_node_events
state_transition_events
clarification_events
prompt_events
llm_calls
retrieval_events
eval_runs
```

## chunks

```text
id
document_id
chunk_text
source_doc
page_number
section
doc_type
region
branch
service_type
policy_type
effective_date
search_vector
embedding vector(384)
metadata_json
created_at
```

## conversation_state

```text
id
session_id
state_json
pending_intent
missing_fields_json
clarification_turn_count
awaiting_user_input
awaiting_confirmation
updated_at
```

## clarification_events

```text
id
trace_id
session_id
original_query
missing_slots_json
clarification_question
clarification_answer
canonical_query
next_route
created_at
```

## prompt_events

```text
id
trace_id
prompt_name
prompt_version
prompt_hash
prompt_inputs_redacted
rendered_prompt_preview
model
provider
created_at
```

## graph_node_events

```text
id
trace_id
node_name
input_state_summary
output_state_summary
route_decision
latency_ms
status
error_message
created_at
```

---

# 21. API Endpoints

## Health

```text
GET /api/health
```

## Chat

```text
POST /api/chat
GET /api/conversations/{session_id}
GET /api/conversations/{session_id}/state
```

## Documents

```text
POST /api/documents/upload
POST /api/documents/seed
GET /api/documents
DELETE /api/documents/{document_id}
POST /api/documents/{document_id}/reindex
```

## Chunks

```text
GET /api/chunks
GET /api/chunks/{chunk_id}
```

## Retrieval

```text
POST /api/retrieval/test
```

## HITL

```text
GET /api/hitl/pending
POST /api/hitl/{id}/approve
POST /api/hitl/{id}/reject
POST /api/hitl/{id}/edit
```

## Tools

```text
GET /api/tools
POST /api/tools/{tool_name}/test
PATCH /api/tools/{tool_name}
```

## Prompts

```text
GET /api/prompts
GET /api/prompts/{prompt_name}
POST /api/prompts/validate
GET /api/prompts/{prompt_name}/traces
```

## Evals

```text
POST /api/evals/run
GET /api/evals
GET /api/evals/{eval_run_id}
```

## Monitoring

```text
GET /api/traces
GET /api/traces/{trace_id}
GET /api/traces/{trace_id}/graph
GET /api/traces/{trace_id}/retrieval
GET /api/traces/{trace_id}/prompts
GET /api/traces/{trace_id}/tools
GET /api/traces/{trace_id}/clarification
```

## Mock Booking API

```text
POST /mock/bookings
GET /mock/bookings/{booking_id}
PATCH /mock/bookings/{booking_id}
```

---

# 22. Streamlit Pages

Required pages:

```text
1_Chat.py
2_Knowledge_Upload.py
3_Chunk_Explorer.py
4_Retrieval_Debugger.py
5_HITL_Review.py
6_Tool_Registry.py
7_Evals.py
8_Monitoring.py
9_Prompt_Audit.py
10_Conversation_State.py
```

Keep UI simple. Do not build a complex custom frontend.

---

# 23. Dependency List

## Runtime Python Dependencies

Use these:

```text
fastapi
uvicorn[standard]
pydantic
pydantic-settings
sqlalchemy
alembic
psycopg[binary]
pgvector
python-dotenv
httpx
tenacity
structlog
orjson
python-multipart
jinja2
pyyaml

langgraph
langchain-core
litellm

llama-index-core
llama-index-readers-file
llama-index-vector-stores-postgres
llama-index-embeddings-fastembed
llama-index-retrievers-bm25

fastembed
onnxruntime

pypdf
streamlit
pandas
pytest
pytest-asyncio
```

Do not include in runtime:

```text
sentence-transformers
torch
ragas
promptfoo
crewai
agentscope
mem0ai
```

---

# 24. Docker Requirements

## docker-compose services

Required:

```text
postgres
api
streamlit
litellm
```

Optional separate eval service:

```text
eval
```

Do not include Langfuse self-host stack in default compose.

## Required command

```bash
docker compose up
```

This should start the V1 app.

## Required ports

```text
FastAPI: 8000
Streamlit: 8501
Postgres: 5432
LiteLLM: 4000
```

---

# 25. Repo Structure

```text
meridian-assistant/
  README.md
  PRD_BRD.md
  docker-compose.yml
  Dockerfile.api
  Dockerfile.ui
  Dockerfile.eval
  .env.example
  pyproject.toml

  prompts/
    registry.yaml
    system/
      assistant_system.yaml
      safety_policy.yaml
    routing/
      classify_intent.yaml
      extract_slots.yaml
      route_decision.yaml
    clarification/
      ask_clarification.yaml
      build_canonical_query.yaml
      missing_slot_policy.yaml
    rag/
      grounded_answer.yaml
      citation_answer.yaml
      retrieval_query_rewrite.yaml
    booking/
      collect_missing_fields.yaml
      booking_confirmation.yaml
      reschedule_confirmation.yaml
      cancellation_confirmation.yaml
    handoff/
      handoff_summary.yaml
      emergency_handoff.yaml
    eval/
      judge_answer_support.yaml
      judge_tool_correctness.yaml

  app/
    main.py
    config.py

    prompts/
      manager.py
      schemas.py
      renderer.py

    api/
      routes_chat.py
      routes_documents.py
      routes_chunks.py
      routes_retrieval.py
      routes_hitl.py
      routes_tools.py
      routes_prompts.py
      routes_evals.py
      routes_traces.py
      routes_mock_booking.py

    graph/
      state.py
      nodes.py
      build_graph.py
      clarification.py

    rag/
      ingestion.py
      chunking.py
      hybrid_retriever.py
      citation.py
      schemas.py

    tools/
      base.py
      registry.py
      schemas.py
      adapters/
        service_area.py
        booking.py
        handoff.py

    db/
      session.py
      models.py
      migrations/

    observability/
      tracing.py
      local_trace.py
      langfuse_optional.py
      logging.py
      redaction.py

    evals/
      runner.py
      metrics.py
      redteam_cases.jsonl
      golden_set.jsonl
      clarification_cases.jsonl

  streamlit_app/
    Home.py
    pages/
      1_Chat.py
      2_Knowledge_Upload.py
      3_Chunk_Explorer.py
      4_Retrieval_Debugger.py
      5_HITL_Review.py
      6_Tool_Registry.py
      7_Evals.py
      8_Monitoring.py
      9_Prompt_Audit.py
      10_Conversation_State.py

  tests/
    test_service_area.py
    test_hybrid_retrieval.py
    test_booking_flow.py
    test_confirmation_gate.py
    test_handoff.py
    test_tool_registry.py
    test_prompt_manager.py
    test_clarification_flow.py
    test_eval_cases.py

  data/
    client_docs/
    seed/
```

---

# 26. Implementation Phases for Codex

## Phase 1: Skeleton

Build:

* FastAPI app
* Streamlit app
* Docker Compose
* Postgres with pgvector
* health endpoint

Acceptance:

```text
docker compose up works
GET /api/health returns OK
Streamlit opens
Postgres connection works
pgvector extension enabled
```

---

## Phase 2: Database

Build models and migrations.

Acceptance:

```text
alembic upgrade head works
all required tables created
```

---

## Phase 3: Prompt Manager

Build:

* prompt YAML schema
* prompt registry loader
* prompt renderer
* prompt hash generator
* prompt validation endpoint
* prompt audit UI page

Acceptance:

```text
all prompts load from /prompts
no hardcoded prompts in graph nodes
prompt validation passes
prompt audit UI lists prompts
LLM traces include prompt_name, version, and hash
```

---

## Phase 4: Conversation State and Clarification

Build:

* conversation_state table
* state loader/saver
* missing slot detection
* ask_clarification node
* build_canonical_query node
* clarification event logging
* conversation state UI page

Acceptance:

```text
ambiguous pricing query asks follow-up before retrieval
ambiguous service-area query asks for ZIP and service type
follow-up answer is merged with original query
canonical query is generated
canonical query routes to correct retrieval/tool path
conversation state is visible in UI
```

---

## Phase 5: Document Seeding and Ingestion

Build:

* seed from existing PDFs
* upload endpoint
* chunking
* metadata extraction
* dense embedding with FastEmbed
* Postgres full-text vector
* pgvector storage

Acceptance:

```text
client PDFs are ingested
chunks are visible
embeddings are stored
search_vector is populated
```

---

## Phase 6: Hybrid Retrieval

Build:

* dense retrieval
* lexical retrieval
* RRF fusion
* metadata filters
* citation mapping

Acceptance:

```text
retrieval debugger shows dense, lexical, fused results
pricing questions retrieve pricing rows
FAQ questions retrieve Q&A chunks
policy questions retrieve policy sections
trace logs include retrieval debug data
canonical query is used for clarified queries
```

---

## Phase 7: Structured Service Area

Build structured tables and service-area tool.

Acceptance:

```text
ZIP/service eligibility is deterministic
20147 plumbing returns sub-contracted restriction
unsupported ZIP routes to manager/handoff path
```

---

## Phase 8: LangGraph

Build graph nodes and routes.

Acceptance:

```text
FAQ goes to RAG
pricing with missing item goes to clarification
service area with missing ZIP goes to clarification
service area with ZIP and service goes to lookup
booking goes to booking flow
emergency goes to handoff
write tools blocked before confirmation
graph node traces are visible in backend and UI
```

---

## Phase 9: Mock Booking API and Tools

Build mock endpoints and tool adapters.

Acceptance:

```text
create booking works after confirmation
booking lookup works
reschedule works after confirmation
cancel works after confirmation
tool invocations are traceable
```

---

## Phase 10: Streamlit UI

Build required pages.

Acceptance:

```text
chat works
upload works
chunks visible
retrieval debugger works
HITL works
tool registry works
monitoring works
prompt audit works
conversation state page works
evals page works
```

---

## Phase 11: Observability

Build trace logging.

Acceptance:

```text
every request has trace_id
traces include graph path, prompt versions, retrieval results, clarification events, tool calls, and final answer
monitoring UI can inspect trace details
Langfuse optional integration does not break local mode
```

---

## Phase 12: Evals

Build pytest eval harness.

Acceptance:

```text
golden_set.jsonl exists
clarification_cases.jsonl exists
redteam_cases.jsonl exists
pytest evals run
eval_results.md generated
eval result includes prompt versions used
```

---

## Phase 13: Documentation

Create:

```text
README.md
ARCHITECTURE.md
PATH_TO_PRODUCTION.md
DEBUGGING_METHODOLOGY.md
GUARDRAILS.md
PROMPT_AUDIT.md
```

Acceptance:

```text
reviewer can run the project from README
framework choices are justified
debugging flow is documented
prompt audit process is documented
clarification flow is documented
what was deliberately left out is documented
```

---

# 27. Final Acceptance Criteria

The V1 is complete when:

```text
1. docker compose up starts Postgres, API, Streamlit, and LiteLLM.
2. No sentence-transformers or torch in runtime image.
3. Hybrid retrieval is always enabled.
4. FastEmbed + pgvector dense retrieval works.
5. Postgres full-text/BM25 lexical retrieval works.
6. RRF fusion works.
7. Client PDFs are ingested.
8. Chunks are visible in UI.
9. Retrieval debugger shows dense, lexical, and fused results.
10. Answers include citations.
11. Ambiguous queries trigger focused clarification.
12. Follow-up answers are merged with original query into a canonical query.
13. Canonical query routes to retrieval/tool path.
14. Service-area eligibility uses structured lookup.
15. Booking creation works after confirmation.
16. Booking lookup works.
17. Reschedule/cancel works after confirmation.
18. Emergency, complaint, fee dispute, and commercial inquiry route to handoff.
19. Every request is traced.
20. Every prompt is loaded from /prompts.
21. Prompt version/hash is attached to every LLM trace.
22. Backend logs are structured and trace_id-linked.
23. Monitoring UI can inspect graph, retrieval, prompt, clarification, state, and tool traces.
24. Evals run from provided customer-message examples.
25. Clarification evals exist.
26. Red-team pytest cases exist.
27. README and path-to-production docs are complete.
```

---

# 28. What Is Deliberately Left Out

Do not build in V1:

```text
full enterprise auth
real CRM integration
real production Booking API
payment collection
voice/call-center integration
long-term memory
Mem0
Kafka
Kubernetes
custom React UI
custom vector database
GraphRAG
cross-encoder reranker
fine-tuned LLM
runtime promptfoo
runtime ragas
self-hosted Langfuse stack
arbitrary UI-created external tools
```

---

# 29. Path to Production

To productionize later:

```text
replace local Postgres with managed Postgres
add auth/RBAC
add branch-level permissions
add document approval workflow
add scheduled eval jobs
add Langfuse Cloud or enterprise observability
add real Booking API credentials
add CRM/ticketing handoff integration
add PII redaction policy
add rate limiting
add backups
add audit logs
add deployment pipeline
add prompt review workflow
add prompt approval gates
add branch-specific policy approval workflow
```

The V1 should be designed so these upgrades do not require rewriting LangGraph, RAG, prompts, state management, clarification flow, or tool adapters.

---

# 30. Final Design Summary

Build one accurate, optimized, and debuggable V1:

```text
LangGraph for orchestration
Stateful clarification for incomplete queries
Hybrid retrieval for accuracy
FastEmbed instead of sentence-transformers
Postgres + pgvector for storage
Postgres full-text/BM25 for exact retrieval
RRF for fusion
Structured lookup for service area
Pydantic schemas for tools
Prompt files under /prompts for auditability
Streamlit for UI
Local Postgres tracing by default
Optional Langfuse Cloud integration
pytest-based eval and red-team suite
```

The system should be light enough to run in Docker, accurate enough for the case study, traceable enough for debugging, graceful enough to handle incomplete user input, and modular enough to scale later.
