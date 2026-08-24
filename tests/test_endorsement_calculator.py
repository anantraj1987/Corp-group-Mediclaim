from datetime import date
from decimal import Decimal

from schemas.gmc_schemas import EndorsementLine
from services.endorsement_calculator import calculate_account_health, calculate_line_item


def test_sample_addition_and_deletion_reconcile_cd_balance():
    policy_end = date(2026, 12, 31)
    endorsement_date = date(2026, 7, 1)
    addition = calculate_line_item(
        EndorsementLine(
            employee_identifier_anonymized="<ANON_EMP_9041>",
            action_type="NEW_HIRE_ADDITION",
            members_covered=["SELF", "SPOUSE"],
            coverage_effective_date=date(2026, 6, 15),
            base_premium_inr=Decimal("6575.34"),
        ),
        policy_end,
        endorsement_date,
    )
    deletion = calculate_line_item(
        EndorsementLine(
            employee_identifier_anonymized="<ANON_EMP_4412>",
            action_type="RESIGNATION_DELETION",
            members_removed=["SELF", "SPOUSE"],
            coverage_cessation_date=date(2026, 6, 30),
            base_premium_inr=Decimal("6049.31"),
        ),
        policy_end,
        endorsement_date,
    )

    assert addition.gst_18_percent_inr == Decimal("1183.56")
    assert addition.total_premium_impact_inr == Decimal("7758.90")
    assert deletion.gst_18_percent_inr == Decimal("1088.88")
    assert deletion.total_premium_impact_inr == Decimal("-7138.19")

    health = calculate_account_health(
        Decimal("120000.00"), [addition, deletion], Decimal("25000.00")
    )
    assert health.net_premium_adjustment_inr == Decimal("620.71")
    assert health.closing_cd_balance_inr == Decimal("119379.29")
    assert health.cd_replenishment_alert is False
