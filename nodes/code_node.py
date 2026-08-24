import json
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def code_analysis_node(state: IncidentState) -> dict:
    """Node: Analyzes git commits, stack traces, and code repositories."""
    logger.info("--- [NODE] Code Analysis Agent ---")
    
    git_data = {}
    if settings.GIT_FILE_PATH.exists():
        with open(settings.GIT_FILE_PATH, "r") as f:
            git_data = json.load(f)
            
    return {
        "code_analysis_data": git_data,
        "visited_nodes": ["code_analysis_node"],
        "execution_logs": ["Analyzed Git commits and stack traces"]
    }
