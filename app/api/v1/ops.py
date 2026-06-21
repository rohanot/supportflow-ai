from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceFlowError
from app.db.models import (
    ClarificationEvent,
    BranchHours,
    Chunk,
    ConversationState,
    Document,
    ServiceArea,
    EvalRun,
    GraphNodeEvent,
    PromptEvent,
    RetrievalEvent,
    StateTransitionEvent,
    ToolInvocation,
    Trace,
    TraceEvent,
)
from app.db.session import get_db
from app.observability.redaction import redact_value
from app.prompts.manager import PromptManager
from app.rag.ingestion import ingest_directory, ingest_pdf_path

router = APIRouter(prefix="/v1", tags=["ops"])
UPLOAD_DIR = Path("sl_docs/uploads")


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)) -> list[dict[str, object]]:
    rows = db.execute(select(Document).order_by(Document.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "source_doc": row.source_doc,
            "title": row.title,
            "doc_type": row.doc_type,
            "region": row.region,
            "branch": row.branch,
            "service_type": row.service_type,
        }
        for row in rows
    ]


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, object]:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise ServiceFlowError("Only PDF uploads are supported for V1 ingestion.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / filename
    content = await file.read()
    target.write_bytes(content)
    report = ingest_pdf_path(target, db=db)
    return _report_to_dict(report)


@router.post("/documents/seed")
def seed_documents(db: Session = Depends(get_db)) -> dict[str, object]:
    reports = ingest_directory(Path("sl_docs"), db=db)
    return {
        "status": "completed",
        "document_count": len(reports),
        "reports": [_report_to_dict(report) for report in reports],
    }


@router.post("/documents/{document_id}/reindex")
def reindex_document(document_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} was not found.")
    source_path = Path(document.source_path or "")
    if not source_path.exists():
        source_path = Path("sl_docs") / document.source_doc
    if not source_path.exists():
        raise NotFoundError(f"Source PDF for document {document_id} was not found.")
    report = ingest_pdf_path(source_path, db=db)
    return _report_to_dict(report)


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} was not found.")
    source_doc = document.source_doc
    db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    db.execute(delete(ServiceArea).where(ServiceArea.source_doc == source_doc))
    db.execute(delete(BranchHours).where(BranchHours.source_doc == source_doc))
    db.delete(document)
    db.commit()
    return {"deleted": True, "document_id": document_id, "source_doc": source_doc}


@router.get("/chunks")
def list_chunks(db: Session = Depends(get_db), limit: int = Query(25, ge=1, le=100)) -> list[dict[str, object]]:
    rows = db.execute(select(Chunk).order_by(Chunk.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "document_id": row.document_id,
            "source_doc": row.source_doc,
            "page_number": row.page_number,
            "section": row.section,
            "doc_type": row.doc_type,
            "region": row.region,
            "branch": row.branch,
            "service_type": row.service_type,
            "policy_type": row.policy_type,
            "snippet": row.chunk_text[:300],
        }
        for row in rows
    ]


@router.get("/prompts")
def list_prompts() -> list[dict[str, object]]:
    manager = PromptManager()
    records = []
    for name in manager.list_prompts():
        record = manager.load_prompt(name)
        records.append(
            {
                "name": name,
                "active_version": record.entry.active_version,
                "path": str(record.path),
                "definition_version": record.definition.version,
                "purpose": record.definition.purpose,
            }
        )
    return records


@router.get("/traces")
def list_traces(db: Session = Depends(get_db), limit: int = Query(25, ge=1, le=100)) -> list[dict[str, object]]:
    rows = db.execute(select(Trace).order_by(Trace.id.desc()).limit(limit)).scalars().all()
    return [_redact_trace_summary(row) for row in rows]


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    trace = db.execute(select(Trace).where(Trace.trace_id == trace_id)).scalar_one_or_none()
    return {
        "trace": None
        if trace is None
        else _redact_trace_summary(trace),
        "events": _rows(db, TraceEvent, trace_id),
        "graph": _rows(db, GraphNodeEvent, trace_id),
        "retrieval": _rows(db, RetrievalEvent, trace_id),
        "prompts": _rows(db, PromptEvent, trace_id),
        "tools": _rows(db, ToolInvocation, trace_id),
        "state_transitions": _rows(db, StateTransitionEvent, trace_id),
    }


@router.get("/traces/{trace_id}/graph")
def get_trace_graph(trace_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return _rows(db, GraphNodeEvent, trace_id)


@router.get("/traces/{trace_id}/retrieval")
def get_trace_retrieval(trace_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return _rows(db, RetrievalEvent, trace_id)


@router.get("/traces/{trace_id}/prompts")
def get_trace_prompts(trace_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return _rows(db, PromptEvent, trace_id)


@router.get("/traces/{trace_id}/tools")
def get_trace_tools(trace_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return _rows(db, ToolInvocation, trace_id)


@router.get("/traces/{trace_id}/clarification")
def get_trace_clarification(trace_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return _rows(db, ClarificationEvent, trace_id)


@router.get("/conversation-state")
def list_conversation_state(
    db: Session = Depends(get_db), limit: int = Query(25, ge=1, le=100)
) -> list[dict[str, object]]:
    rows = db.execute(select(ConversationState).order_by(ConversationState.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "session_id": row.session_id,
            "pending_intent": row.pending_intent,
            "missing_fields": row.missing_fields_json,
            "awaiting_user_input": row.awaiting_user_input,
            "awaiting_confirmation": row.awaiting_confirmation,
            "state": row.state_json,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


@router.get("/evals")
def list_eval_runs(db: Session = Depends(get_db), limit: int = Query(25, ge=1, le=100)) -> list[dict[str, object]]:
    rows = db.execute(select(EvalRun).order_by(EvalRun.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "eval_name": row.eval_name,
            "total_cases": row.total_cases,
            "passed_cases": row.passed_cases,
            "failed_cases": row.failed_cases,
            "metrics": row.metrics_json,
            "results_path": row.results_path,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.post("/evals/run")
def run_evals(db: Session = Depends(get_db)) -> dict[str, object]:
    summary = run_scenario_eval()
    results_path = "eval_results.md"
    write_eval_results(Path(results_path), summary)
    row = EvalRun(
        eval_name=str(summary.get("eval_name", "serviceflow_scenario_v1")),
        prompt_versions_json=dict(summary.get("prompt_versions") or {}),
        total_cases=int(summary.get("total_cases") or 0),
        passed_cases=int(summary.get("passed_cases") or 0),
        failed_cases=int(summary.get("failed_cases") or 0),
        metrics_json=dict(summary.get("metrics") or {}),
        results_path=results_path,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    output = dict(summary)
    output["id"] = row.id
    output["results_path"] = results_path
    return output


def _rows(db: Session, model: type, trace_id: str) -> list[dict[str, object]]:
    rows = db.execute(select(model).where(model.trace_id == trace_id).order_by(model.id.asc())).scalars().all()
    return [_public_columns(row) for row in rows]


def _public_columns(row: object) -> dict[str, object]:
    output: dict[str, object] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        output[column.name] = redact_value(value)
    return output


def _redact_trace_summary(row: Trace) -> dict[str, object]:
    return {
        "trace_id": row.trace_id,
        "session_id": row.session_id,
        "intent": row.intent,
        "pending_intent": row.pending_intent,
        "original_query": redact_value(row.original_query),
        "clarification_question": redact_value(row.clarification_question),
        "clarification_answer": redact_value(row.clarification_answer),
        "canonical_query": redact_value(row.canonical_query),
        "graph_path": row.graph_path,
        "final_response": redact_value(row.final_response),
        "handoff_reason": redact_value(row.handoff_reason),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _report_to_dict(report: object) -> dict[str, object]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    if hasattr(report, "__dataclass_fields__"):
        return asdict(report)
    return dict(report)


def run_scenario_eval() -> dict[str, object]:
    from app.evals.runner import run_scenario_eval as _run_scenario_eval

    return _run_scenario_eval()


def write_eval_results(path: Path, summary: dict[str, object]) -> None:
    from app.evals.runner import write_eval_results as _write_eval_results

    _write_eval_results(path, summary)
