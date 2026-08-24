from datetime import date
from decimal import Decimal
from typing import Iterable

from schemas.gmc_schemas import (
    EndorsementDocket,
    EndorsementLine,
    EndorsementSummary,
    PolicyTerms,
    ProcessedLineItem,
    CashDepositAccountHealth,
    RejectedException,
)
from services.endorsement_calculator import calculate_account_health, calculate_line_item
from guardrails.output_validator import validate_endorsement_docket


def assemble_docket(
    endorsement_id: str,
    endorsement_effective_date: date,
    policy: PolicyTerms,
    approved_lines: Iterable[EndorsementLine],
    rejected_exceptions: Iterable[RejectedException] = (),
    processed_items: list[ProcessedLineItem] | None = None,
    account_health: CashDepositAccountHealth | None = None,
) -> EndorsementDocket:
    processed_items = processed_items or [
        calculate_line_item(
            line,
            policy_end_date=policy.policy_end_date,
            endorsement_effective_date=endorsement_effective_date,
            gst_rate_percent=policy.gst_rate_percent,
        )
        for line in approved_lines
    ]
    exceptions = list(rejected_exceptions)
    health = account_health or calculate_account_health(
        policy.cd_balance_inr, processed_items, policy.cd_alert_threshold_inr
    )
    additions = sum(
        item.action_type in {"NEW_HIRE_ADDITION", "LIFE_EVENT_ADDITION", "DEPENDENT_MODIFICATION"}
        for item in processed_items
    )
    deletions = sum(item.action_type == "RESIGNATION_DELETION" for item in processed_items)

    docket = EndorsementDocket(
        endorsement_id=endorsement_id,
        corporate_account=policy.corporate_account,
        endorsement_effective_date=endorsement_effective_date,
        endorsement_summary=EndorsementSummary(
            additions_processed=additions,
            deletions_processed=deletions,
            exceptions_flagged=len(exceptions),
        ),
        processed_line_items=processed_items,
        rejected_exceptions=exceptions,
        cash_deposit_account_health=health,
        guardrails_validation_status="FAILED",
    )
    docket.guardrails_validation_status = (
        "PASSED" if not validate_endorsement_docket(docket) else "FAILED"
    )
    return docket
