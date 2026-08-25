import requests
from typing import Dict, Any
from config.settings import settings
from utils.logger import logger


class RemoteMCPClient:
    """HTTP Client Bridge connecting LangGraph to remote MCP Microservices."""

    def __init__(self):
        self.enabled = True
        self.services = {
            "gmc_actuarial": settings.MCP_GMC_ACTUARIAL_URL,
        }

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def call_mcp_service(self, service_key: str, tool_name: str, arguments: dict = None) -> Dict[str, Any]:
        """Invocates a tool on a remote MCP HTTP microservice."""
        if not self.enabled:
            return {"status": "fallback", "message": "MCP service is disabled."}
        if arguments is None:
            arguments = {}

        base_url = self.services.get(service_key)
        if not base_url:
            logger.error(f"[MCP CLIENT] Unknown MCP service key: '{service_key}'")
            return {"error": f"Service key '{service_key}' not registered."}

        endpoint = f"{base_url}/mcp/invoke"
        payload = {"tool_name": tool_name, "arguments": arguments}

        try:
            logger.info(f"[MCP CLIENT] Connecting to HTTP MCP Microservice at {endpoint}...")
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()
            logger.info(f"[MCP CLIENT] Remote MCP Service returned status {response.status_code}")
            return data.get("result", data)
        except requests.exceptions.RequestException as e:
            logger.warning(f"[MCP CLIENT] Remote MCP microservice at {base_url} unreachable ({str(e)}). Using local fallback.")
            return {"status": "fallback", "message": f"MCP microservice at {base_url} offline."}


mcp_remote_client = RemoteMCPClient()
    