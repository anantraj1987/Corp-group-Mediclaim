from decimal import Decimal

from schemas.gmc_schemas import EndorsementDocket


def validate_endorsement_docket(docket: EndorsementDocket) -> list[str]:
    """Run deterministic interceptors against an assembled endorsement docket."""
    errors: list[str] = []

    for item in docket.processed_line_items:
        if not item.employee_identifier_anonymized.startswith("<ANON_"):
            errors.append("Processed line contains a non-anonymized employee identifier.")
        if "TBD" in (
            item.pro_rata_base_premium_inr,
            item.gst_18_percent_inr,
            item.total_premium_impact_inr,
        ):
            errors.append("Actuarial calculation is unavailable for a processed line.")

    health = docket.cash_deposit_account_health
    health_values = (
        health.opening_cd_balance_inr,
        health.net_premium_adjustment_inr,
        health.closing_cd_balance_inr,
    )
    if any(value == "TBD" for value in health_values) or health.cd_replenishment_alert == "TBD":
        errors.append("CD health calculation is unavailable.")
    else:
        line_total = sum(
            (item.total_premium_impact_inr for item in docket.processed_line_items),
            Decimal("0"),
        )
        if health.net_premium_adjustment_inr != line_total:
            errors.append("CD net adjustment does not reconcile with processed line totals.")
        if health.closing_cd_balance_inr != health.opening_cd_balance_inr - health.net_premium_adjustment_inr:
            errors.append("CD closing balance does not reconcile with opening balance and net adjustment.")
        if health.closing_cd_balance_inr < 0:
            errors.append("CD closing balance is negative.")

    expected_additions = sum(
        item.action_type in {"NEW_HIRE_ADDITION", "LIFE_EVENT_ADDITION", "DEPENDENT_MODIFICATION"}
        for item in docket.processed_line_items
    )
    expected_deletions = sum(
        item.action_type == "RESIGNATION_DELETION"
        for item in docket.processed_line_items
    )
    if docket.endorsement_summary.additions_processed != expected_additions:
        errors.append("Addition count does not match processed lines.")
    if docket.endorsement_summary.deletions_processed != expected_deletions:
        errors.append("Deletion count does not match processed lines.")
    if docket.endorsement_summary.exceptions_flagged != len(docket.rejected_exceptions):
        errors.append("Exception count does not match rejected exceptions.")

    return errors