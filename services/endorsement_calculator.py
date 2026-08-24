from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from schemas.gmc_schemas import CashDepositAccountHealth, EndorsementLine, ProcessedLineItem


MONEY_QUANTUM = Decimal("0.01")


class CashDepositOverdraftError(ValueError):
    """Raised when an endorsement would make the CD account negative."""


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def inclusive_days(start: date, end: date) -> int:
    if end < start:
        return 0
    return (end - start).days + 1


def calculate_line_item(
    line: EndorsementLine,
    policy_end_date: date,
    endorsement_effective_date: date,
    gst_rate_percent: Decimal = Decimal("18"),
) -> ProcessedLineItem:
    if line.action_type in {"NEW_HIRE_ADDITION", "LIFE_EVENT_ADDITION", "DEPENDENT_MODIFICATION"}:
        effective_date = line.coverage_effective_date or endorsement_effective_date
        days_remaining = inclusive_days(effective_date, policy_end_date)
        base_premium = money(line.base_premium_inr)
        gst = money(base_premium * gst_rate_percent / Decimal("100"))
        return ProcessedLineItem(
            employee_identifier_anonymized=line.employee_identifier_anonymized,
            action_type=line.action_type,
            members_covered=line.members_covered,
            coverage_effective_date=effective_date,
            active_days_remaining=days_remaining,
            pro_rata_base_premium_inr=base_premium,
            gst_18_percent_inr=gst,
            total_premium_impact_inr=money(base_premium + gst),
            status="APPROVED",
        )

    cessation_date = line.coverage_cessation_date or endorsement_effective_date
    unexpired_start_date = cessation_date.fromordinal(cessation_date.toordinal() + 1)
    days_unexpired = inclusive_days(unexpired_start_date, policy_end_date)
    base_credit = money(line.base_premium_inr)
    gst_credit = money(base_credit * gst_rate_percent / Decimal("100"))
    return ProcessedLineItem(
        employee_identifier_anonymized=line.employee_identifier_anonymized,
        action_type=line.action_type,
        members_removed=line.members_removed,
        coverage_cessation_date=cessation_date,
        unexpired_days=days_unexpired,
        pro_rata_base_premium_inr=base_credit,
        gst_18_percent_inr=gst_credit,
        total_premium_impact_inr=money(-(base_credit + gst_credit)),
        status="APPROVED",
    )


def calculate_account_health(
    opening_balance_inr: Decimal,
    processed_items: list[ProcessedLineItem],
    alert_threshold_inr: Decimal,
) -> CashDepositAccountHealth:
    net_adjustment = money(sum((item.total_premium_impact_inr for item in processed_items), Decimal("0")))
    closing_balance = money(opening_balance_inr - net_adjustment)
    if closing_balance < 0:
        raise CashDepositOverdraftError(
            f"CD overdraft blocked: closing balance would be {closing_balance}."
        )
    return CashDepositAccountHealth(
        opening_cd_balance_inr=money(opening_balance_inr),
        net_premium_adjustment_inr=net_adjustment,
        closing_cd_balance_inr=closing_balance,
        cd_replenishment_alert=closing_balance < money(alert_threshold_inr),
    )
