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
    assert "batch_id" not in store.get_batch("batch-1")


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


def test_history_store_flags_late_life_event_attempts(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    store.record_enrollment(
        "<ANON_EMP_7120>",
        "2026-01-01",
        ["SELF", "CHILD"],
        {
            "corporate_account": "TechCorp India Pvt Ltd",
            "action_type": "LIFE_EVENT_ADDITION",
            "decision": "REJECTED",
            "outside_life_event_window": True,
        },
    )

    late_attempts = store.get_late_life_event_attempts(
        "TechCorp India Pvt Ltd", date(2026, 1, 1)
    )
    assert len(late_attempts) == 1
    assert late_attempts[0]["employee_identifier"] == "<ANON_EMP_7120>"


def test_history_keeps_context_across_batches_in_one_policy_term(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    term = date(2026, 1, 1)
    state_user_id = store._state_user_id("TechCorp India Pvt Ltd", term)
    store.record_batch(
        "batch-1",
        {
            "corporate_account": "TechCorp India Pvt Ltd",
            "policy_start_date": term.isoformat(),
            "endorsement_effective_date": "2026-07-01",
            "closing_cd_balance_inr": "9500.00",
            "state_user_id": state_user_id,
        },
    )
    store.record_enrollment(
        "<ANON_EMP_7120>",
        term.isoformat(),
        ["SELF", "CHILD"],
        {"corporate_account": "TechCorp India Pvt Ltd", "decision": "REJECTED"},
    )

    assert store.get_latest_batch("TechCorp India Pvt Ltd", term)["closing_cd_balance_inr"] == "9500.00"
    assert len(store.get_enrollment_history("TechCorp India Pvt Ltd", term)) == 1


def test_latest_policy_term_snapshot_restores_closing_cd_balance(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    term = date(2026, 1, 1)
    state_user_id = store._state_user_id("TechCorp India Pvt Ltd", term)
    store.record_batch(
        "batch-2",
        {
            "corporate_account": "TechCorp India Pvt Ltd",
            "policy_start_date": term.isoformat(),
            "endorsement_effective_date": "2026-08-01",
            "closing_cd_balance_inr": "96074.29",
            "state_user_id": state_user_id,
        },
    )

    latest = store.get_latest_batch("TechCorp India Pvt Ltd", term)
    assert latest["closing_cd_balance_inr"] == "96074.29"


def test_policy_term_snapshot_survives_store_reinitialization(tmp_path):
    history_path = tmp_path / "memory_history.json"
    first_store = LocalHistoryStore(history_path)
    term = date(2026, 1, 1)
    state_user_id = first_store._state_user_id("TechCorp India Pvt Ltd", term)
    first_store.record_batch(
        "batch-1",
        {
            "corporate_account": "TechCorp India Pvt Ltd",
            "policy_start_date": term.isoformat(),
            "endorsement_effective_date": "2026-07-01",
            "closing_cd_balance_inr": "96074.29",
            "state_user_id": state_user_id,
        },
    )

    second_store = LocalHistoryStore(history_path)
    latest = second_store.get_latest_batch("TechCorp India Pvt Ltd", term)
    assert latest["closing_cd_balance_inr"] == "96074.29"


def test_employee_policy_context_keeps_tree_life_event_and_claims(tmp_path):
    store = LocalHistoryStore(tmp_path / "history.json")
    store.record_enrollment(
        "<ANON_EMP_9041>",
        "2026-01-01",
        ["SELF", "SPOUSE", "CHILD"],
        {
            "corporate_account": "TechCorp India Pvt Ltd",
            "dependent_tree": [{"relationship": "SPOUSE", "date_of_birth": "1992-04-10"}],
            "event_date": "2026-05-01",
            "intimation_date": "2026-05-12",
            "prior_claims": [{"claim_id": "CLM-1", "status": "SETTLED", "amount_inr": "25000"}],
        },
    )

    context = store.get_employee_policy_context(
        "<ANON_EMP_9041>", "TechCorp India Pvt Ltd", date(2026, 1, 1)
    )
    assert context[0]["dependent_tree"][0]["relationship"] == "SPOUSE"
    assert context[0]["life_event"]["event_date"] == "2026-05-01"
    assert context[0]["prior_claims"][0]["status"] == "SETTLED"


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
