from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


Money = Decimal
ActionType = Literal[
    "NEW_HIRE_ADDITION",
    "LIFE_EVENT_ADDITION",
    "RESIGNATION_DELETION",
    "DEPENDENT_MODIFICATION",
]
LineStatus = Literal["APPROVED", "REJECTED"]


class PolicyTerms(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    corporate_account: str = Field(min_length=1)
    policy_start_date: date
    policy_end_date: date
    sum_insured_inr: Money = Field(gt=0)
    family_definition: Literal["1+3", "1+5"] = "1+3"
    gst_rate_percent: Decimal = Field(default=Decimal("18"), ge=0, le=100)
    life_event_window_days: int = Field(default=30, ge=0)
    cd_balance_inr: Money = Field(ge=0)
    cd_alert_threshold_inr: Money = Field(ge=0)

    @field_validator("policy_end_date")
    @classmethod
    def end_after_start(cls, value: date, info):
        start = info.data.get("policy_start_date")
        if start and value < start:
            raise ValueError("policy_end_date must be on or after policy_start_date")
        return value


class CensusMember(BaseModel):
    corporate_account: Optional[str] = None
    employee_identifier: str = Field(min_length=1)
    corporate_email: Optional[str] = None
    aadhaar: Optional[str] = None
    date_of_birth: Optional[date] = None
    action_type: ActionType
    members: List[str] = Field(default_factory=list)
    coverage_effective_date: Optional[date] = None
    coverage_cessation_date: Optional[date] = None
    event_date: Optional[date] = None
    intimation_date: Optional[date] = None
    dependent_tree: List[Dict[str, Any]] = Field(default_factory=list)
    prior_claims: List[Dict[str, Any]] = Field(default_factory=list)
    base_premium_inr: Money = Field(default=Decimal("0"), ge=0)


class CensusIngestionResult(BaseModel):
    records: List[CensusMember] = Field(default_factory=list)
    row_errors: List[Dict[str, Any]] = Field(default_factory=list)
    source_format: Literal["csv", "xlsx"]


class EndorsementLine(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employee_identifier_anonymized: str = Field(min_length=1)
    action_type: ActionType
    members_covered: List[str] = Field(default_factory=list)
    members_removed: List[str] = Field(default_factory=list)
    coverage_effective_date: Optional[date] = None
    coverage_cessation_date: Optional[date] = None
    event_date: Optional[date] = None
    intimation_date: Optional[date] = None
    base_premium_inr: Money = Field(ge=0)
    status: LineStatus = "APPROVED"
    rejection_reason: Optional[str] = None
    sla_reference: Optional[str] = None


class ProcessedLineItem(BaseModel):
    employee_identifier_anonymized: str
    email: Optional[str] = None
    dob: Optional[str] = None
    aadhaar: Optional[str] = None
    action_type: ActionType
    members_covered: List[str] = Field(default_factory=list)
    members_removed: List[str] = Field(default_factory=list)
    coverage_effective_date: Optional[date] = None
    coverage_cessation_date: Optional[date] = None
    active_days_remaining: int = Field(default=0, ge=0)
    unexpired_days: int = Field(default=0, ge=0)
    pro_rata_base_premium_inr: Money | Literal["TBD"] = Decimal("0.00")
    gst_18_percent_inr: Money | Literal["TBD"] = Decimal("0.00")
    total_premium_impact_inr: Money | Literal["TBD"] = Decimal("0.00")
    status: LineStatus


class RejectedException(BaseModel):
    employee_identifier_anonymized: str
    email: Optional[str] = None
    dob: Optional[str] = None
    aadhaar: Optional[str] = None
    attempted_action: ActionType
    rejection_reason: str
    sla_reference: Optional[str] = None


class CashDepositAccountHealth(BaseModel):
    opening_cd_balance_inr: Money | Literal["TBD"]
    net_premium_adjustment_inr: Money | Literal["TBD"]
    closing_cd_balance_inr: Money | Literal["TBD"]
    cd_replenishment_alert: bool | Literal["TBD"]


class EndorsementSummary(BaseModel):
    additions_processed: int = Field(ge=0)
    deletions_processed: int = Field(ge=0)
    exceptions_flagged: int = Field(ge=0)


class GuardrailInterceptor(BaseModel):
    name: str
    status: Literal["PASSED", "FAILED"]
    messages: List[str] = Field(default_factory=list)


class EndorsementDocket(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    endorsement_id: str
    corporate_account: str
    endorsement_effective_date: date
    endorsement_summary: EndorsementSummary
    processed_line_items: List[ProcessedLineItem]
    rejected_exceptions: List[RejectedException]
    cash_deposit_account_health: CashDepositAccountHealth
    guardrails_validation_status: Literal["PASSED", "FAILED"] = "FAILED"
    guardrails_interceptors: List[GuardrailInterceptor] = Field(default_factory=list)
