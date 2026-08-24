from datetime import date
from decimal import Decimal

import pytest

from schemas.gmc_schemas import EndorsementLine
from services.actuarial_tools import calculate_deletion_credit, calculate_pro_rata_premium
from services.endorsement_calculator import CashDepositOverdraftError, calculate_account_health, calculate_line_item
from services.memory_service import LocalHistoryStore


def test_history_store_is_idempotent(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    assert store.record_batch("batch-1", {"approved_count": 1}) is True
    assert store.record_batch("batch-1", {"approved_count": 99}) is False
    assert store.get_batch("batch-1")["approved_count"] == 1


def test_history_store_tracks_family_structures_by_policy_term(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    assert store.record_enrollment(
        "EMP-9041",
        "2026-01-01",
        ["SELF", "SPOUSE"],
        {"corporate_account": "TechCorp India Pvt Ltd", "action_type": "NEW_HIRE_ADDITION"},
    ) is True

    history = store.get_enrollment_history(
        "TechCorp India Pvt Ltd", date(2026, 1, 1)
    )
    assert history[0]["employee_identifier"] == "EMP-9041"
    assert history[0]["members"] == ["SELF", "SPOUSE"]


def test_sample_actuarial_tools_preserve_decimal_results():
    addition = calculate_pro_rata_premium(
        Decimal("6575.34"), date(2026, 6, 15), date(2026, 12, 31), date(2026, 7, 1)
    )
    deletion = calculate_deletion_credit(
        Decimal("6049.31"), date(2026, 6, 30), date(2026, 12, 31), date(2026, 7, 1)
    )
    assert addition.total_premium_impact_inr == Decimal("7758.90")
    assert deletion.unexpired_days == 184
    assert deletion.total_premium_impact_inr == Decimal("-7138.19")


def test_annual_premium_is_prorated_over_policy_term():
    addition = calculate_pro_rata_premium(
        Decimal("0"),
        date(2026, 6, 15),
        date(2026, 12, 31),
        date(2026, 7, 1),
        annual_premium_inr=Decimal("12000"),
        policy_start_date=date(2026, 1, 1),
    )
    assert addition.active_days_remaining == 200
    assert addition.pro_rata_base_premium_inr == Decimal("6575.34")
    assert addition.gst_18_percent_inr == Decimal("1183.56")
    assert addition.total_premium_impact_inr == Decimal("7758.90")


def test_overdraft_is_blocked():
    item = calculate_line_item(
        EndorsementLine(
            employee_identifier_anonymized="<ANON_EMP_TEST>",
            action_type="NEW_HIRE_ADDITION",
            base_premium_inr=Decimal("100.00"),
        ),
        date(2026, 12, 31),
        date(2026, 7, 1),
    )
    with pytest.raises(CashDepositOverdraftError):
        calculate_account_health(Decimal("0.00"), [item], Decimal("0.00"))
