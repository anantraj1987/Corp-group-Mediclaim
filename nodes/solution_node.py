from graph.state import IncidentState
from services.openai_service import openai_service
from utils.logger import logger


def generate_solution_node(state: IncidentState) -> dict:
    """Node: Synthesizes solution using domain context AND stored Mem0 user preferences."""
    logger.info("--- [NODE] Solution Generator (Mem0 Preferences Aware) ---")

    # Format user preferences retrieved from Mem0
    preferences_list = state.get("user_preferences", [])
    if preferences_list:
        preferences_str = "\n".join([f"- {pref}" for pref in preferences_list])
    else:
        preferences_str = "No specific technical preferences recorded for this user."

    system_prompt = (
        "You are an expert IT Incident Resolution Engineer. Synthesize the provided query, "
        "domain context, telemetry, or codebase information into a clear remediation plan.\n\n"
        "IMPORTANT USER PREFERENCES:\n"
        f"{preferences_str}\n\n"
        "Ensure your solution aligns with these explicit preferences whenever applicable.\n"
        "Include: 1. Root Cause Analysis 2. Step-by-Step Resolution Steps."
    )

    context = (
        f"User: {state['user_name']}\n"
        f"Query: {state['raw_query']}\n"
        f"Intent: {state['intent']} ({state['sub_category']})\n"
        f"Auth/KB Context: {state.get('retrieved_docs', [])}\n"
        f"Telemetry: {state.get('telemetry_data', {})}\n"
        f"Code Data: {state.get('code_analysis_data', {})}\n"
        f"Billing Data: {state.get('billing_data', {})}\n"
        f"Previous Human Feedback: {state.get('human_feedback', 'None')}"
    )

    solution = openai_service.execute_prompt(system_prompt=system_prompt, user_input=context)

    # Increment retry count if iterating through a loop
    new_retry_count = state.get("retry_count", 0) + (1 if state.get("visited_nodes", []).count("generate_solution_node") > 0 else 0)

    return {
        "solution": solution,
        "retry_count": new_retry_count,
        "visited_nodes": ["generate_solution_node"],
        "execution_logs": [f"Generated solution tailored to user preferences (Attempt {new_retry_count + 1})"]
    }

