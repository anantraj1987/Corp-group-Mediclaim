
from typing import Literal
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def route_by_intent(state: IncidentState) -> Literal["auth_node", "monitoring_node", "code_node", "billing_node", "kb_node"]:
    """
    Conditional Edge: Routes execution dynamically based on identified Intent.
    """
    intent = state.get("intent", "General")
    logger.info(f"[ROUTER] Dynamic Branching Evaluation for Intent: '{intent}'")
    
    if intent == "Authentication":
        return "auth_node"
    elif intent == "Infrastructure":
        return "monitoring_node"
    elif intent == "Code":
        return "code_node"
    elif intent == "Billing":
        return "billing_node"
    else:
        return "kb_node"


def evaluate_confidence_route(state: IncidentState) -> Literal["END", "human_approval_node", "solution_node"]:
    """
    Conditional Edge: Evaluates solution confidence against thresholds to route toward
    Termination, Human Approval, or Automated Retry loops.
    """
    confidence = state.get("confidence_score", 0)
    retry_count = state.get("retry_count", 0)
    human_approved = state.get("human_approved", False)
    
    logger.info(f"[ROUTER] Confidence Check: Score={confidence}, Threshold={settings.CONFIDENCE_THRESHOLD}, Retry={retry_count}")
    
    if confidence >= settings.CONFIDENCE_THRESHOLD or human_approved:
        return "END"
    
    if retry_count < settings.MAX_RETRY_COUNT:
        logger.warning(f"[ROUTER] Low confidence detected ({confidence}%). Triggering self-correction loop.")
        return "solution_node"
    else:
        logger.warning(f"[ROUTER] Max retries ({settings.MAX_RETRY_COUNT}) reached without acceptable confidence. Escalating.")
        return "human_approval_node"


