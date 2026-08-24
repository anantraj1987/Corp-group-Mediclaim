from datetime import date
from decimal import Decimal

from schemas.gmc_schemas import (
    CashDepositAccountHealth,
    EndorsementLine,
    PolicyTerms,
    ProcessedLineItem,
    RejectedException,
)
from guardrails.output_validator import validate_endorsement_docket
from services.docket_assembler import assemble_docket


def test_docket_matches_sample_structure():
    policy = PolicyTerms(
        corporate_account="<ANON_CORP_TECHCORP>",
        policy_start_date=date(2026, 1, 1),
        policy_end_date=date(2026, 12, 31),
        sum_insured_inr=Decimal("500000"),
        family_definition="1+3",
        cd_balance_inr=Decimal("120000"),
        cd_alert_threshold_inr=Decimal("25000"),
    )
    docket = assemble_docket(
        "END-2026-CORP-0482",
        date(2026, 7, 1),
        policy,
        [
            EndorsementLine(
                employee_identifier_anonymized="<ANON_EMP_9041>",
                action_type="NEW_HIRE_ADDITION",
                members_covered=["SELF", "SPOUSE"],
                coverage_effective_date=date(2026, 6, 15),
                base_premium_inr=Decimal("6575.34"),
            ),
            EndorsementLine(
                employee_identifier_anonymized="<ANON_EMP_4412>",
                action_type="RESIGNATION_DELETION",
                members_removed=["SELF", "SPOUSE"],
                coverage_cessation_date=date(2026, 6, 30),
                base_premium_inr=Decimal("6049.31"),
            ),
        ],
        [
            RejectedException(
                employee_identifier_anonymized="<ANON_EMP_7120>",
                attempted_action="LIFE_EVENT_ADDITION",
                rejection_reason="Late intimation",
                sla_reference="GMC Master SLA Clause 6.4 - Life Event Window",
            ),
            RejectedException(
                employee_identifier_anonymized="<ANON_EMP_3108>",
                attempted_action="DEPENDENT_MODIFICATION",
                rejection_reason="Cross-selection breach",
                sla_reference="GMC Master SLA Clause 4.2 - Family Definition",
            ),
        ],
    )

    assert docket.model_dump()["endorsement_summary"] == {
        "additions_processed": 1,
        "deletions_processed": 1,
        "exceptions_flagged": 2,
    }
    assert docket.cash_deposit_account_health.closing_cd_balance_inr == Decimal("119379.29")
    assert docket.guardrails_validation_status == "PASSED"


def test_tbd_actuarial_values_fail_output_guardrail():
    policy = PolicyTerms(
        corporate_account="<ANON_CORP_TECHCORP>",
        policy_start_date=date(2026, 1, 1),
        policy_end_date=date(2026, 12, 31),
        sum_insured_inr=Decimal("500000"),
        cd_balance_inr=Decimal("120000"),
        cd_alert_threshold_inr=Decimal("25000"),
    )
    line = EndorsementLine(
        employee_identifier_anonymized="<ANON_EMP_9041>",
        action_type="NEW_HIRE_ADDITION",
        coverage_effective_date=date(2026, 6, 15),
        base_premium_inr=Decimal("6575.34"),
    )
    processed_items = [
        ProcessedLineItem(
            employee_identifier_anonymized=line.employee_identifier_anonymized,
            action_type=line.action_type,
            coverage_effective_date=line.coverage_effective_date,
            pro_rata_base_premium_inr="TBD",
            gst_18_percent_inr="TBD",
            total_premium_impact_inr="TBD",
            status="APPROVED",
        )
    ]
    health = CashDepositAccountHealth(
        opening_cd_balance_inr="TBD",
        net_premium_adjustment_inr="TBD",
        closing_cd_balance_inr="TBD",
        cd_replenishment_alert="TBD",
    )
    docket = assemble_docket(
        "END-TBD",
        date(2026, 7, 1),
        policy,
        [line],
        processed_items=processed_items,
        account_health=health,
    )

    assert docket.guardrails_validation_status == "FAILED"
    assert validate_endorsement_docket(docket)
