from pydantic import BaseModel, Field
from graph.state import IncidentState
from services.openai_service import openai_service
from utils.logger import logger


class IntentClassificationSchema(BaseModel):
    intent: str = Field(
        description="Category: Authentication, Infrastructure, Code, Billing, or General"
    )
    sub_category: str = Field(description="Sub-category (e.g., Password, CPU, Memory, NPE, AWS Cost)")


def classify_intent_node(state: IncidentState) -> dict:
    """Node: Analyzes incident description and determines category."""
    logger.info("--- [NODE] Intent Classification ---")
    
    system_prompt = (
        "You are an expert IT Helpdesk Intent Classifier. Analyze the user's issue and classify it into "
        "exactly one category: 'Authentication', 'Infrastructure', 'Code', 'Billing', or 'General'. "
        "Also extract a concise sub-category."
    )
    
    response: IntentClassificationSchema = openai_service.execute_prompt(
        system_prompt=system_prompt,
        user_input=state["raw_query"],
        output_schema=IntentClassificationSchema
    )
    
    logger.info(f"Classified Intent: {response.intent} (Sub: {response.sub_category})")
    
    return {
        "intent": response.intent,
        "sub_category": response.sub_category,
        "visited_nodes": ["classify_intent_node"],
        "execution_logs": [f"Intent classified as {response.intent}"]
    }

