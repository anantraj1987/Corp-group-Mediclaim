from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from services.openai_service import OpenAIService
from utils.logger import logger


class JudgeVerdict(BaseModel):
    verdict: str = Field(description="Either 'CORRECT' or 'INCORRECT'.")
    reasoning: str = Field(description="One-sentence justification for the verdict.")


def evaluate_guardrail_compliance(run: Any, example: Any) -> dict:
    """Deterministic check that the assembled docket cleared every guardrail interceptor."""
    outputs = run.outputs or {}
    status = outputs.get("guardrails_validation_status", "FAILED")
    interceptor_messages = [
        message
        for interceptor in outputs.get("guardrails_interceptors", [])
        for message in interceptor.get("messages", [])
    ]

    score = 1.0 if status == "PASSED" and not interceptor_messages else 0.0
    return {
        "key": "guardrail_compliance",
        "score": score,
        "comment": f"status={status}, messages={interceptor_messages or 'none'}",
    }


def evaluate_docket_correctness(run: Any, example: Any) -> dict:
    """LLM-as-judge comparing the produced endorsement docket against the reference expectation."""
    outputs = run.outputs or {}
    reference = (example.outputs or {}).get("reference_expectation", "")
    if not reference:
        return {"key": "docket_correctness", "score": None, "comment": "No reference expectation provided."}

    summary = {
        "endorsement_summary": outputs.get("endorsement_summary"),
        "guardrails_validation_status": outputs.get("guardrails_validation_status"),
        "cash_deposit_account_health": outputs.get("cash_deposit_account_health"),
        "rejected_exceptions": [
            item.get("rejection_reason") for item in outputs.get("rejected_exceptions", [])
        ],
    }

    try:
        judge = OpenAIService()
        verdict: JudgeVerdict = judge.execute_prompt(
            system_prompt=(
                "You are a GMC endorsement QA judge. Compare the actual processing outcome "
                "against the expected outcome and decide if it matches. Respond CORRECT only "
                "when the summary counts, guardrail status, and any rejection reasons align "
                "with the expectation."
            ),
            user_input=f"Expected outcome: {reference}\n\nActual outcome: {summary}",
            output_schema=JudgeVerdict,
        )
    except Exception as error:
        logger.warning(f"[EVALS] LLM-as-judge unavailable ({type(error).__name__}); skipping.")
        return {"key": "docket_correctness", "score": None, "comment": str(error)}

    score = 1.0 if verdict.verdict.strip().upper() == "CORRECT" else 0.0
    return {"key": "docket_correctness", "score": score, "comment": verdict.reasoning}


def evaluate_cd_balance_reconciliation(run: Any, example: Any) -> dict:
    """Deterministic check that opening/net/closing CD balances reconcile arithmetically."""
    health = (run.outputs or {}).get("cash_deposit_account_health", {})
    opening = health.get("opening_cd_balance_inr")
    net = health.get("net_premium_adjustment_inr")
    closing = health.get("closing_cd_balance_inr")

    if "TBD" in (opening, net, closing):
        return {"key": "cd_balance_reconciliation", "score": 0.0, "comment": "Actuarial calculation unavailable."}

    try:
        reconciles = round(float(closing), 2) == round(float(opening) - float(net), 2)
    except (TypeError, ValueError):
        reconciles = False

    return {
        "key": "cd_balance_reconciliation",
        "score": 1.0 if reconciles else 0.0,
        "comment": f"opening={opening}, net={net}, closing={closing}",
    }
