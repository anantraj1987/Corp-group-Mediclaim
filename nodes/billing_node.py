import json
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def billing_analysis_node(state: IncidentState) -> dict:
    """Node: Queries cloud cost management records."""
    logger.info("--- [NODE] Billing & Cost Agent ---")
    
    billing_data = {}
    if settings.BILLING_FILE_PATH.exists():
        with open(settings.BILLING_FILE_PATH, "r") as f:
            billing_data = json.load(f)
            
    return {
        "billing_data": billing_data,
        "visited_nodes": ["billing_analysis_node"],
        "execution_logs": ["Extracted cost variance and AWS Cost Explorer metrics"]
    }
