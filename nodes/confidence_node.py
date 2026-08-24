from pydantic import BaseModel, Field
from graph.state import IncidentState
from services.openai_service import openai_service
from utils.logger import logger


class ConfidenceRatingSchema(BaseModel):
    confidence_score: int = Field(description="Score between 0 and 100 based on accuracy and completeness")
    reasoning: str = Field(description="Brief explanation of the rating")


def confidence_check_node(state: IncidentState) -> dict:
    """Node: Evaluates the solution confidence score to determine routing."""
    logger.info("--- [NODE] Confidence Assessor ---")
    
    system_prompt = (
        "You are a Quality Assurance Engine for Incident Resolution. Evaluate the solution against "
        "the user query and context. Assign a confidence score from 0 to 100 based on accuracy and completeness."
    )
    
    user_input = f"User Query: {state['raw_query']}\nProposed Solution:\n{state['solution']}"
    
    result: ConfidenceRatingSchema = openai_service.execute_prompt(
        system_prompt=system_prompt,
        user_input=user_input,
        output_schema=ConfidenceRatingSchema
    )
    
    logger.info(f"Assessed Confidence: {result.confidence_score}% - Reasoning: {result.reasoning}")
    
    return {
        "confidence_score": result.confidence_score,
        "visited_nodes": ["confidence_check_node"],
        "execution_logs": [f"Assessed confidence: {result.confidence_score}%"]
    }


