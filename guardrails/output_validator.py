from decimal import Decimal

from schemas.gmc_schemas import EndorsementDocket, GuardrailInterceptor


def run_guardrail_interceptors(docket: EndorsementDocket) -> list[GuardrailInterceptor]:
    """Return deterministic, named guardrail results for the docket output."""
    results: list[GuardrailInterceptor] = []

    anonymization_errors = [
        "Processed line contains a non-anonymized employee identifier."
        for item in docket.processed_line_items
        if not item.employee_identifier_anonymized.startswith("<ANON_")
    ]
    results.append(GuardrailInterceptor(
        name="employee_identifier_anonymization",
        status="FAILED" if anonymization_errors else "PASSED",
        messages=anonymization_errors,
    ))

    actuarial_errors = [
        "Actuarial calculation is unavailable for a processed line."
        for item in docket.processed_line_items
        if "TBD" in (
            item.pro_rata_base_premium_inr,
            item.gst_18_percent_inr,
            item.total_premium_impact_inr,
        )
    ]
    results.append(GuardrailInterceptor(
        name="actuarial_calculation_available",
        status="FAILED" if actuarial_errors else "PASSED",
        messages=actuarial_errors,
    ))

    health = docket.cash_deposit_account_health
    health_errors: list[str] = []
    health_values = (
        health.opening_cd_balance_inr,
        health.net_premium_adjustment_inr,
        health.closing_cd_balance_inr,
    )
    if any(value == "TBD" for value in health_values) or health.cd_replenishment_alert == "TBD":
        health_errors.append("CD health calculation is unavailable.")
    else:
        line_total = sum(
            (item.total_premium_impact_inr for item in docket.processed_line_items),
            Decimal("0"),
        )
        if health.net_premium_adjustment_inr != line_total:
            health_errors.append("CD net adjustment does not reconcile with processed line totals.")
        if health.closing_cd_balance_inr != health.opening_cd_balance_inr - health.net_premium_adjustment_inr:
            health_errors.append("CD closing balance does not reconcile with opening balance and net adjustment.")
        if health.closing_cd_balance_inr < 0:
            health_errors.append("CD closing balance is negative.")
    results.append(GuardrailInterceptor(
        name="cash_deposit_reconciliation",
        status="FAILED" if health_errors else "PASSED",
        messages=health_errors,
    ))

    expected_additions = sum(
        item.action_type in {"NEW_HIRE_ADDITION", "LIFE_EVENT_ADDITION", "DEPENDENT_MODIFICATION"}
        for item in docket.processed_line_items
    )
    expected_deletions = sum(
        item.action_type == "RESIGNATION_DELETION"
        for item in docket.processed_line_items
    )
    summary_errors = []
    if docket.endorsement_summary.additions_processed != expected_additions:
        summary_errors.append("Addition count does not match processed lines.")
    if docket.endorsement_summary.deletions_processed != expected_deletions:
        summary_errors.append("Deletion count does not match processed lines.")
    if docket.endorsement_summary.exceptions_flagged != len(docket.rejected_exceptions):
        summary_errors.append("Exception count does not match rejected exceptions.")
    results.append(GuardrailInterceptor(
        name="docket_summary_consistency",
        status="FAILED" if summary_errors else "PASSED",
        messages=summary_errors,
    ))
    return results


def validate_endorsement_docket(docket: EndorsementDocket) -> list[str]:
    """Run deterministic interceptors against an assembled endorsement docket."""
    return [
        message
        for interceptor in run_guardrail_interceptors(docket)
        for message in interceptor.messages
    ]