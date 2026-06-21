from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class SourceDocument:
    source_doc: str
    path: Path
    doc_type: str
    title: str | None = None
    region: str | None = None
    branch: str | None = None
    service_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    chunk_text: str
    source_doc: str
    page_number: int | None = None
    section: str | None = None
    doc_type: str = "unknown"
    region: str | None = None
    branch: str | None = None
    service_type: str | None = None
    policy_type: str | None = None
    effective_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    search_vector: str | None = None


@dataclass(frozen=True)
class ServiceAreaRecord:
    region: str
    county: str | None
    zip_start: str | None
    zip_end: str | None
    zip_exact: str | None
    hvac_status: str | None
    plumbing_status: str | None
    electrical_status: str | None
    primary_branch: str | None
    overflow_branch: str | None
    restriction_notes: str | None
    source_doc: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchHoursRecord:
    branch: str
    day_of_week: str
    opens_at: str | None
    closes_at: str | None
    timezone: str | None
    source_doc: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionReport:
    source_doc: str
    chunk_count: int
    service_area_count: int
    branch_hours_count: int
    embedding_count: int
    source_path: str
    notes: list[str] = field(default_factory=list)


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: str | None = None
    region: str | None = None
    branch: str | None = None
    service_type: str | None = None
    policy_type: str | None = None
    source_doc: str | None = None


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    canonical_query: str | None = None
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    top_k: int = 5
    include_debug: bool = False


class RetrievalResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    chunk_id: int
    document_id: int
    source_doc: str
    page_number: int | None = None
    section: str | None = None
    doc_type: str | None = None
    region: str | None = None
    branch: str | None = None
    service_type: str | None = None
    policy_type: str | None = None
    snippet: str
    dense_rank: int | None = None
    lexical_rank: int | None = None
    dense_score: float | None = None
    lexical_score: float | None = None
    fused_score: float | None = None


class DenseResult(RetrievalResult):
    pass


class LexicalResult(RetrievalResult):
    pass


class FusedResult(RetrievalResult):
    pass


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    document_id: int
    source_doc: str
    page_number: int | None = None
    section: str | None = None
    doc_type: str | None = None
    snippet: str
    score: float


class RetrievalDebugInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str | None = None
    embedding_backend: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    vector_search_mode: str | None = None
    eval_data_excluded: bool | None = None
    dense_top_k: int | None = None
    lexical_top_k: int | None = None
    final_top_k: int | None = None
    latency_ms: int | None = None
    dense_query: str | None = None
    normalized_query: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    dense_candidate_count: int | None = None
    lexical_candidate_count: int | None = None
    fused_candidate_count: int | None = None
    selected_chunk_ids: list[int] = Field(default_factory=list)
    selected_source_docs: list[str] = Field(default_factory=list)
    confidence_reasons: list[str] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    query: str
    canonical_query: str | None = None
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    dense_results: list[DenseResult] = Field(default_factory=list)
    lexical_results: list[LexicalResult] = Field(default_factory=list)
    fused_results: list[FusedResult] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float
    confidence_reasons: list[str] = Field(default_factory=list)
    debug: RetrievalDebugInfo = Field(default_factory=RetrievalDebugInfo)
