from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.rag.schemas import BranchHoursRecord, ChunkRecord, ServiceAreaRecord, SourceDocument

SECTION_SPLIT_RE = re.compile(r"\n{2,}")
ZIP_RE = re.compile(r"\b\d{5}\b")
DAY_RE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:\+?\$[\d,]+|Quote required)", re.IGNORECASE)
DEFAULT_RAG_EXCLUDED_DOC_TYPES = {"test_data", "eval_data"}


def infer_document_profile(path: Path) -> SourceDocument:
    name = path.name.lower()
    if "service_area" in name:
        doc_type = "service_area"
    elif "pricing" in name:
        doc_type = "pricing"
    elif "warranty" in name:
        doc_type = "policy"
    elif "cancellation" in name:
        doc_type = "policy"
    elif "branch_hours" in name:
        doc_type = "branch_hours"
    elif "faq" in name:
        doc_type = "faq"
    elif "booking_api_spec" in name:
        doc_type = "booking_api_spec"
    elif "customer_messages" in name:
        doc_type = "eval_data"
    else:
        doc_type = "document"
    return SourceDocument(source_doc=path.name, path=path, doc_type=doc_type, title=path.stem.replace("_", " ").title())


def is_default_retrieval_candidate(doc_type: str | None) -> bool:
    return doc_type not in DEFAULT_RAG_EXCLUDED_DOC_TYPES


def normalize_search_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]+", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_sections(text: str) -> list[str]:
    sections = [section.strip() for section in SECTION_SPLIT_RE.split(text) if section.strip()]
    return sections or ([text.strip()] if text.strip() else [])


def chunk_pricing_text(text: str, source_doc: str) -> list[ChunkRecord]:
    row_chunks = _chunk_pricing_rows(text, source_doc)
    if row_chunks:
        return row_chunks
    chunks: list[ChunkRecord] = []
    for section in split_sections(text):
        lines = [line.strip("-• \t") for line in section.splitlines() if line.strip()]
        for line in lines:
            if any(keyword in line.lower() for keyword in ["fee", "tier", "replacement", "maintenance", "surcharge", "upgrade"]):
                chunks.append(
                    ChunkRecord(
                        chunk_text=line,
                        source_doc=source_doc,
                        doc_type="pricing",
                        section="pricing",
                        metadata={"chunk_key": hash_text(line)},
                        search_vector=normalize_search_text(line),
                    )
                )
    if chunks:
        return chunks
    return generic_chunks(text, source_doc, doc_type="pricing", section="pricing")


def _chunk_pricing_rows(text: str, source_doc: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    header_tokens = {
        "service",
        "price range",
        "notes",
        "common services",
        "repair tiers",
        "tier",
        "description",
        "maintenance plans",
        "plan",
        "annual fee",
        "includes",
    }
    for section in split_sections(text):
        lines = [line.strip("-â€¢ \t") for line in section.splitlines() if line.strip()]
        consumed: set[int] = set()
        for index, line in enumerate(lines):
            lowered = line.lower()
            if index in consumed or lowered in header_tokens:
                continue
            price_index = _next_price_line_index(lines, index)
            if price_index is None:
                continue
            row_lines = [line, *lines[index + 1 : price_index + 1]]
            consumed.update(range(index + 1, price_index + 1))
            note_index = price_index + 1
            if note_index < len(lines) and _is_pricing_note_line(lines, note_index, header_tokens):
                row_lines.append(lines[note_index])
                consumed.add(note_index)
            row_text = "\n".join(row_lines)
            chunks.append(
                ChunkRecord(
                    chunk_text=row_text,
                    source_doc=source_doc,
                    doc_type="pricing",
                    section="pricing",
                    metadata={"chunk_key": hash_text(row_text)},
                    search_vector=normalize_search_text(row_text),
                )
            )
    return chunks


def _next_price_line_index(lines: list[str], index: int) -> int | None:
    for candidate in range(index + 1, min(index + 4, len(lines))):
        if PRICE_RE.search(lines[candidate]):
            return candidate
    return None


def _is_pricing_note_line(lines: list[str], index: int, header_tokens: set[str]) -> bool:
    line = lines[index]
    lowered = line.lower()
    if lowered in header_tokens:
        return False
    if PRICE_RE.search(line):
        return True
    if any(
        token in lowered
        for token in [
            "extra",
            "included",
            "required",
            "excluded",
            "inspection",
            "permit",
            "quote",
            "supplied",
            "discount",
            "priority",
            "tune-up",
        ]
    ):
        return True
    if _next_price_line_index(lines, index) is not None:
        return False
    return False


def chunk_faq_text(text: str, source_doc: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    qas = re.split(r"\n(?=Q:)", text, flags=re.IGNORECASE)
    for qa in qas:
        qa = qa.strip()
        if not qa:
            continue
        chunks.append(
            ChunkRecord(
                chunk_text=qa,
                source_doc=source_doc,
                doc_type="faq",
                section="qa",
                metadata={"chunk_key": hash_text(qa)},
                search_vector=normalize_search_text(qa),
            )
        )
    return chunks or generic_chunks(text, source_doc, doc_type="faq", section="qa")


def chunk_policy_text(text: str, source_doc: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for section in split_sections(text):
        chunks.append(
            ChunkRecord(
                chunk_text=section,
                source_doc=source_doc,
                doc_type="policy",
                section="policy",
                metadata={"chunk_key": hash_text(section)},
                search_vector=normalize_search_text(section),
            )
        )
    return chunks


def chunk_booking_api_text(text: str, source_doc: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for section in split_sections(text):
        if section.startswith(("GET ", "POST ", "PATCH ", "DELETE ")):
            chunks.append(
                ChunkRecord(
                    chunk_text=section,
                    source_doc=source_doc,
                    doc_type="booking_api_spec",
                    section="endpoint",
                    metadata={"chunk_key": hash_text(section)},
                    search_vector=normalize_search_text(section),
                )
            )
    return chunks or generic_chunks(text, source_doc, doc_type="booking_api_spec", section="api")


def chunk_customer_message_text(text: str, source_doc: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        chunks.append(
            ChunkRecord(
                chunk_text=line,
                source_doc=source_doc,
                doc_type="eval_data",
                section="message",
                metadata={"chunk_key": hash_text(line)},
                search_vector=normalize_search_text(line),
            )
        )
    return chunks or generic_chunks(text, source_doc, doc_type="customer_message", section="message")


def chunk_branch_hours_text(text: str, source_doc: str) -> tuple[list[ChunkRecord], list[BranchHoursRecord]]:
    chunks: list[ChunkRecord] = []
    records: list[BranchHoursRecord] = []
    current_branch = None
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        lowered = line.lower()
        if "branch" in lowered and ":" in line:
            current_branch = line.split(":", 1)[1].strip()
            continue
        if DAY_RE.match(line):
            chunks.append(
                ChunkRecord(
                    chunk_text=line,
                    source_doc=source_doc,
                    doc_type="branch_hours",
                    section="hours",
                    metadata={"chunk_key": hash_text(line)},
                    search_vector=normalize_search_text(line),
                )
            )
            times = re.findall(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\b", line)
            records.append(
                BranchHoursRecord(
                    branch=current_branch or "unknown",
                    day_of_week=DAY_RE.match(line).group(0) if DAY_RE.match(line) else "unknown",
                    opens_at=times[0] if times else None,
                    closes_at=times[1] if len(times) > 1 else None,
                    timezone="local",
                    source_doc=source_doc,
                    metadata={"chunk_key": hash_text(line)},
                )
            )
    return chunks or generic_chunks(text, source_doc, doc_type="branch_hours", section="hours"), records


def chunk_service_area_text(text: str, source_doc: str) -> tuple[list[ChunkRecord], list[ServiceAreaRecord]]:
    chunks: list[ChunkRecord] = []
    records: list[ServiceAreaRecord] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if ZIP_RE.search(line) or any(token in line.lower() for token in ["hvac", "plumbing", "electrical", "primary branch", "overflow"]):
            chunks.append(
                ChunkRecord(
                    chunk_text=line,
                    source_doc=source_doc,
                    doc_type="service_area",
                    section="service_area",
                    metadata={"chunk_key": hash_text(line)},
                    search_vector=normalize_search_text(line),
                )
            )
    if not chunks:
        chunks = generic_chunks(text, source_doc, doc_type="service_area", section="service_area")
    for line in lines:
        zips = ZIP_RE.findall(line)
        if not zips:
            continue
        records.append(
            ServiceAreaRecord(
                region="unknown",
                county=None,
                zip_start=zips[0],
                zip_end=zips[-1] if len(zips) > 1 else zips[0],
                zip_exact=zips[0] if len(zips) == 1 else None,
                hvac_status="unknown",
                plumbing_status="unknown",
                electrical_status="unknown",
                primary_branch=None,
                overflow_branch=None,
                restriction_notes=line,
                source_doc=source_doc,
                metadata={"chunk_key": hash_text(line)},
            )
        )
    return chunks, records


def generic_chunks(text: str, source_doc: str, doc_type: str = "document", section: str | None = None) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for section_text in split_sections(text):
        chunks.append(
            ChunkRecord(
                chunk_text=section_text,
                source_doc=source_doc,
                doc_type=doc_type,
                section=section,
                metadata={"chunk_key": hash_text(section_text)},
                search_vector=normalize_search_text(section_text),
            )
        )
    return chunks


def chunk_document_text(text: str, source_doc: str, doc_type: str) -> tuple[list[ChunkRecord], list[ServiceAreaRecord], list[BranchHoursRecord]]:
    if doc_type == "service_area":
        chunks, service_areas = chunk_service_area_text(text, source_doc)
        return chunks, service_areas, []
    if doc_type == "pricing":
        return chunk_pricing_text(text, source_doc), [], []
    if doc_type == "faq":
        return chunk_faq_text(text, source_doc), [], []
    if doc_type == "policy":
        return chunk_policy_text(text, source_doc), [], []
    if doc_type == "branch_hours":
        chunks, branch_hours = chunk_branch_hours_text(text, source_doc)
        return chunks, [], branch_hours
    if doc_type == "booking_api_spec":
        return chunk_booking_api_text(text, source_doc), [], []
    if doc_type in {"customer_messages", "eval_data", "test_data"}:
        return chunk_customer_message_text(text, source_doc), [], []
    return generic_chunks(text, source_doc), [], []
