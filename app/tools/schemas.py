from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ServiceType = Literal["hvac", "plumbing", "electrical"]


class ServiceAreaLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zip_code: str = Field(min_length=5, max_length=5)
    service_type: ServiceType

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 5:
            raise ValueError("zip_code must be exactly 5 digits")
        return value

    @field_validator("service_type", mode="before")
    @classmethod
    def normalize_service_type(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("service_type is required")
        return value.strip().lower()


class ServiceAreaLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    zip_code: str
    service_type: ServiceType
    region: str | None = None
    county: str | None = None
    service_status: str
    primary_branch: str | None = None
    overflow_branch: str | None = None
    restrictions: list[str] = Field(default_factory=list)
    handoff_required: bool = False
    handoff_reason: str | None = None
    source_doc: str | None = None
    trace_id: str


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str | None = None
    customer_info: dict[str, object] | None = None
    service_type: ServiceType
    job_type: str = Field(min_length=1)
    zip_code: str = Field(min_length=5, max_length=5)
    preferred_date: str = Field(min_length=1)
    preferred_window: str = Field(min_length=1)
    preferred_tech: str | None = None
    notes: str | None = None
    channel: str = Field(min_length=1)
    confirmed_by_user: bool = False

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 5:
            raise ValueError("zip_code must be exactly 5 digits")
        return value

    @field_validator("service_type", mode="before")
    @classmethod
    def normalize_service_type(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("service_type is required")
        return value.strip().lower()

    @model_validator(mode="after")
    def require_customer_identifier(self) -> "BookingCreateRequest":
        if not self.customer_id and not self.customer_info:
            raise ValueError("customer_id or customer_info is required")
        return self


class BookingPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["reschedule", "cancel", "update_notes"]
    new_date: str | None = None
    new_window: str | None = None
    cancel_reason: str | None = None
    notes: str | None = None
    confirmed_by_user: bool = False

    @model_validator(mode="after")
    def validate_action_fields(self) -> "BookingPatchRequest":
        if self.action == "reschedule" and (not self.new_date or not self.new_window):
            raise ValueError("new_date and new_window are required for reschedule")
        if self.action == "cancel" and not self.cancel_reason:
            raise ValueError("cancel_reason is required for cancel")
        if self.action == "update_notes" and self.notes is None:
            raise ValueError("notes are required for update_notes")
        return self
