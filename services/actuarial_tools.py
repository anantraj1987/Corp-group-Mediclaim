from datetime import date
from decimal import Decimal

from schemas.gmc_schemas import CashDepositAccountHealth, EndorsementLine, ProcessedLineItem
from services.endorsement_calculator import (
    calculate_account_health,
    calculate_line_item,
    inclusive_days,
    money,
)


def _prorated_base_premium(
    annual_premium_inr: Decimal,
    coverage_start: date,
    policy_start_date: date,
    policy_end_date: date,
) -> Decimal:
    policy_days = inclusive_days(policy_start_date, policy_end_date)
    covered_days = inclusive_days(coverage_start, policy_end_date)
    if policy_days == 0:
        return money(Decimal("0"))
    return money(annual_premium_inr * Decimal(covered_days) / Decimal(policy_days))


def calculate_pro_rata_premium(
    base_premium_inr: Decimal,
    effective_date: date,
    policy_end_date: date,
    endorsement_effective_date: date,
    gst_rate_percent: Decimal = Decimal("18"),
    annual_premium_inr: Decimal | None = None,
    policy_start_date: date | None = None,
) -> ProcessedLineItem:
    if annual_premium_inr is not None and policy_start_date is not None:
        base_premium_inr = _prorated_base_premium(
            annual_premium_inr,
            effective_date,
            policy_start_date,
            policy_end_date,
        )
    return calculate_line_item(
        EndorsementLine(
            employee_identifier_anonymized="<TOOL_INPUT>",
            action_type="NEW_HIRE_ADDITION",
            coverage_effective_date=effective_date,
            base_premium_inr=base_premium_inr,
        ),
        policy_end_date,
        endorsement_effective_date,
        gst_rate_percent,
    )


def calculate_deletion_credit(
    base_premium_inr: Decimal,
    cessation_date: date,
    policy_end_date: date,
    endorsement_effective_date: date,
    gst_rate_percent: Decimal = Decimal("18"),
    annual_premium_inr: Decimal | None = None,
    policy_start_date: date | None = None,
) -> ProcessedLineItem:
    if annual_premium_inr is not None and policy_start_date is not None:
        unexpired_start = cessation_date.fromordinal(cessation_date.toordinal() + 1)
        base_premium_inr = _prorated_base_premium(
            annual_premium_inr,
            unexpired_start,
            policy_start_date,
            policy_end_date,
        )
    return calculate_line_item(
        EndorsementLine(
            employee_identifier_anonymized="<TOOL_INPUT>",
            action_type="RESIGNATION_DELETION",
            coverage_cessation_date=cessation_date,
            base_premium_inr=base_premium_inr,
        ),
        policy_end_date,
        endorsement_effective_date,
        gst_rate_percent,
    )


def calculate_cd_health(
    opening_balance_inr: Decimal,
    processed_items: list[ProcessedLineItem],
    alert_threshold_inr: Decimal,
) -> CashDepositAccountHealth:
    return calculate_account_health(opening_balance_inr, processed_items, alert_threshold_inr)