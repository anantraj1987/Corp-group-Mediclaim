from datetime import date
from decimal import Decimal

from schemas.gmc_schemas import PolicyTerms
from services.family_rules import validate_family_members, validate_life_event_window


POLICY = PolicyTerms(
    corporate_account="<ANON_CORP_TECHCORP>",
    policy_start_date=date(2026, 1, 1),
    policy_end_date=date(2026, 12, 31),
    sum_insured_inr=Decimal("500000"),
    family_definition="1+3",
    cd_balance_inr=Decimal("120000"),
    cd_alert_threshold_inr=Decimal("25000"),
)


def test_parent_cross_selection_is_rejected():
    exceptions = validate_family_members(
        "<ANON_EMP_3108>",
        ["SELF", "SPOUSE", "PARENT", "PARENT_IN_LAW"],
        POLICY,
        sla_reference="[Source: techcorp_sla.txt | Clause: Clause 4.2]",
    )
    assert len(exceptions) == 1
    assert "Cross-selection breach" in exceptions[0].rejection_reason
    assert exceptions[0].sla_reference == "[Source: techcorp_sla.txt | Clause: Clause 4.2]"


def test_late_newborn_is_rejected_after_30_days():
    exception = validate_life_event_window(
        "<ANON_EMP_7120>",
        "LIFE_EVENT_ADDITION",
        date(2026, 1, 1),
        date(2026, 5, 22),
        POLICY,
    )
    assert exception is not None
    assert "141 days" in exception.rejection_reason


def test_event_intimated_within_window_is_accepted():
    assert validate_life_event_window(
        "<ANON_EMP_1>",
        "LIFE_EVENT_ADDITION",
        date(2026, 6, 1),
        date(2026, 7, 1),
        POLICY,
    ) is None
