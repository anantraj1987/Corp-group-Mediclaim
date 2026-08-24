import json
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def auth_analysis_node(state: IncidentState) -> dict:
    """Node: Fetches relevant identity/auth KB protocols."""
    logger.info("--- [NODE] Authentication Agent ---")
    
    docs = []
    if settings.KB_FILE_PATH.exists():
        with open(settings.KB_FILE_PATH, "r") as f:
            kb = json.load(f)
            docs = [item for item in kb if item.get("category") == "Authentication"]
            
    return {
        "retrieved_docs": docs,
        "visited_nodes": ["auth_analysis_node"],
        "execution_logs": ["Retrieved identity and authentication protocols"]
    }
