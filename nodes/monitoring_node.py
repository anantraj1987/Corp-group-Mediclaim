import json
from graph.state import IncidentState
from config.settings import settings
from utils.logger import logger


def monitoring_telemetry_node(state: IncidentState) -> dict:
    """Node: Pulls CloudWatch/Datadog infrastructure telemetry."""
    logger.info("--- [NODE] Monitoring & Infrastructure Agent ---")
    
    telemetry = {}
    if settings.MONITORING_FILE_PATH.exists():
        with open(settings.MONITORING_FILE_PATH, "r") as f:
            telemetry = json.load(f)
            
    return {
        "telemetry_data": telemetry,
        "visited_nodes": ["monitoring_telemetry_node"],
        "execution_logs": ["Pulled infrastructure metrics and CloudWatch alerts"]
    }

