from graph.state import IncidentState
from services.mcp_client import mcp_remote_client
from utils.logger import logger


def mcp_execution_node(state: IncidentState) -> dict:
    """Node: Issues remote HTTP calls to separate MCP Microservice ports based on detected intent."""
    logger.info("--- [NODE] Remote MCP Tool Execution Node ---")
    intent = state.get("intent", "General")

    visited = ["mcp_execution_node"]

    if intent == "Infrastructure":
        logger.info("[MCP NODE] Routing to Remote Monitoring Microservice (Port 8001)...")
        res = mcp_remote_client.call_mcp_service(
            service_key="monitoring",
            tool_name="query_ec2_metrics",
            arguments={"resource_id": "i-0a8f912c4b1112e"}
        )
        return {
            "telemetry_data": res,
            "visited_nodes": visited,
            "execution_logs": ["Invoked Monitoring MCP Microservice over HTTP (Port 8001)"]
        }

    elif intent == "Code":
        logger.info("[MCP NODE] Routing to Remote GitHub Microservice (Port 8002)...")
        res = mcp_remote_client.call_mcp_service(
            service_key="github",
            tool_name="analyze_git_commits",
            arguments={"repo_name": "core-payment-service"}
        )
        return {
            "code_analysis_data": res,
            "visited_nodes": visited,
            "execution_logs": ["Invoked GitHub MCP Microservice over HTTP (Port 8002)"]
        }

    elif intent == "Billing":
        logger.info("[MCP NODE] Routing to Remote Billing Microservice (Port 8003)...")
        res = mcp_remote_client.call_mcp_service(
            service_key="billing",
            tool_name="inspect_aws_cost_explorer",
            arguments={}
        )
        return {
            "billing_data": res,
            "visited_nodes": visited,
            "execution_logs": ["Invoked Billing MCP Microservice over HTTP (Port 8003)"]
        }

    return {
        "visited_nodes": visited,
        "execution_logs": ["Default MCP node completed"]
    }
