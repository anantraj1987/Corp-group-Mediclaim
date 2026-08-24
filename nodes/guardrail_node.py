# nodes/guardrail_node.py

from graph.state import IncidentState
from presidio_governance.anonymizer import presidio_anonymizer_service
from presidio_governance.rehydrator import presidio_rehydrator_service
from guardrails.schema_validator import schema_validator
from guardrails.injection_detector import injection_detector
from guardrails.policy_enforcer import policy_enforcer
from utils.logger import logger


def input_guardrail_node(state: IncidentState) -> dict:
    """
    Pre-Ingestion Entry Guardrail:
    1. Schema & Length Validation
    2. Prompt Injection Defense
    3. Microsoft Presidio ML Reversible Anonymization
    4. Compliance Policy Enforcement
    """
    logger.info("--- [SECURITY GUARDRAIL] Executing Pre-Ingestion Presidio Governance ---")
    raw_query = state.get("raw_query", "")

    # 1. Schema Validation
    is_valid, schema_msg = schema_validator.validate_input_query(raw_query)
    if not is_valid:
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": f"Schema Validation Failed: {schema_msg}",
            "solution": f"⛔ SECURITY BLOCK: Input query rejected. {schema_msg}",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": [f"Input blocked by schema validator: {schema_msg}"]
        }

    # 2. Prompt Injection Attack Check
    if injection_detector.is_injection_attack(raw_query):
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": "Adversarial Prompt Injection Detected.",
            "solution": "⛔ SECURITY BLOCK: Prompt Injection attempt rejected.",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": ["Adversarial prompt injection pattern blocked."]
        }

    # 3. Microsoft Presidio ML Anonymization (Tokens generated)
    sanitized_query, token_map = presidio_anonymizer_service.anonymize_and_map(raw_query)

    # 4. Policy Compliance Check on Sanitized Query
    policy_result = policy_enforcer.check_policy_compliance(sanitized_query)
    if not policy_result.is_compliant:
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": f"Policy Violation: {policy_result.policy_violation_reason}",
            "solution": f"⛔ SECURITY BLOCK: {policy_result.policy_violation_reason}",
            "confidence_score": 100,
            "visited_nodes": ["input_guardrail_node"],
            "execution_logs": [f"Policy blocked: {policy_result.policy_violation_reason}"]
        }

    logger.info("[SECURITY GUARDRAIL] All Pre-Ingestion Checks & Presidio Anonymization PASSED.")
    return {
        "guardrail_passed": True,
        "guardrail_violation_reason": "",
        "sanitized_query": sanitized_query,
        "presidio_token_map": token_map,  # Pass mapping downstream in state
        "visited_nodes": ["input_guardrail_node"],
        "execution_logs": ["Pre-ingestion Presidio security guardrail passed."]
    }


def output_guardrail_node(state: IncidentState) -> dict:
    """
    Post-Generation Exit Guardrail:
    1. Re-hydrates Presidio tokens back into real entity values for authorized display.
    """
    logger.info("--- [SECURITY GUARDRAIL] Executing Presidio Output Re-Hydration ---")
    generated_solution = state.get("solution", "")
    token_map = state.get("presidio_token_map", {})

    # Re-hydrate tokens (<ANON_PERSON_xxxx>) back to original names/emails/IPs
    final_rehydrated_solution = presidio_rehydrator_service.rehydrate_text(
        generated_solution, 
        token_map
    )

    return {
        "solution": final_rehydrated_solution,
        "visited_nodes": ["output_guardrail_node"],
        "execution_logs": ["Post-generation Presidio re-hydration completed successfully."]
    }

