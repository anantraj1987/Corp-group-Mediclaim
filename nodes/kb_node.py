import json
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def fallback_kb_node(state: IncidentState) -> dict:
    """Node: Performs generic knowledge base search."""
    logger.info("--- [NODE] Knowledge Base Agent ---")
    
    docs = []
    if settings.KB_FILE_PATH.exists():
        with open(settings.KB_FILE_PATH, "r") as f:
            docs = json.load(f)
            
    return {
        "retrieved_docs": docs,
        "visited_nodes": ["fallback_kb_node"],
        "execution_logs": ["Performed general knowledge base lookup"]
    }

