#A specialized node that serves as the Input Gateway Filter (executing first) and Output Sanitizer Filter (executing last).
from graph.state import IncidentState
from guardrails.schema_validator import schema_validator
from guardrails.pii_sanitizer import pii_sanitizer
from guardrails.injection_detector import injection_detector
from guardrails.policy_enforcer import policy_enforcer
from utils.logger import logger


def input_guardrail_node(state: IncidentState) -> dict:
    """Entry Node: Validates schema, screens for prompt injections, redacts PII, and enforces policy."""
    logger.info("--- [SECURITY GUARDRAIL] Executing Pre-Ingestion Security Checks ---")
    raw_query = state.get("raw_query", "")

    # 1. Regex & Schema Validation
    is_valid, schema_msg = schema_validator.validate_input_query(raw_query)
    if not is_valid:
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": f"Schema Validation Failed: {schema_msg}",
            "solution": f"⛔ SECURITY BLOCK: Input query rejected. {schema_msg}",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": [f"Blocked by Schema Guardrail: {schema_msg}"]
        }

    # 2. Prompt Injection Detection
    if injection_detector.is_injection_attack(raw_query):
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": "Adversarial Prompt Injection / System Override Detected.",
            "solution": "⛔ SECURITY BLOCK: Adversarial Prompt Injection attempt blocked by Security Engine.",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": ["Blocked by Prompt Injection Guardrail"]
        }

    # 3. PII Redaction
    sanitized_query = pii_sanitizer.sanitize_text(raw_query)

    # 4. Semantic Policy Compliance
    policy_result = policy_enforcer.check_policy_compliance(sanitized_query)
    if not policy_result.is_compliant:
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": f"Policy Violation: {policy_result.policy_violation_reason}",
            "solution": f"⛔ SECURITY BLOCK: Query violates corporate IT policy. Reason: {policy_result.policy_violation_reason}",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": [f"Blocked by Policy Guardrail: {policy_result.policy_violation_reason}"]
        }

    logger.info("[SECURITY GUARDRAIL] All Pre-Ingestion Checks PASSED.")
    return {
        "guardrail_passed": True,
        "sanitized_query": sanitized_query,
        "visited_nodes": ["input_guardrail_node"],
        "execution_logs": ["Passed Pre-Ingestion Security & PII Guardrails"]
    }


def output_guardrail_node(state: IncidentState) -> dict:
    """Exit Node: Sanitizes final solution output to guarantee no credentials or PII leak out."""
    logger.info("--- [SECURITY GUARDRAIL] Executing Post-Generation Output Sanitization ---")
    raw_solution = state.get("solution", "")

    # Redact any accidental credential leak in generated output
    sanitized_solution = pii_sanitizer.sanitize_text(raw_solution)

    return {
        "solution": sanitized_solution,
        "visited_nodes": ["output_guardrail_node"],
        "execution_logs": ["Sanitized output solution for PII/data leakage prevention."]
    }

