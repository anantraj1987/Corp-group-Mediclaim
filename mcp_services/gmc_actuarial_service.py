from datetime import date
from decimal import Decimal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from services.actuarial_tools import (
    calculate_cd_health,
    calculate_deletion_credit,
    calculate_pro_rata_premium,
)
from schemas.gmc_schemas import ProcessedLineItem


app = FastAPI(title="Corporate GMC Actuarial MCP Service", version="1.0.0")


class MCPToolRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "gmc-actuarial-mcp"}


@app.get("/mcp/tools")
def list_tools():
    return {
        "tools": [
            {"name": "calculate_pro_rata_premium"},
            {"name": "calculate_deletion_credit"},
            {"name": "calculate_cd_health"},
        ]
    }


def _decimal(value) -> Decimal:
    return Decimal(str(value))


@app.post("/mcp/invoke")
def invoke_tool(request: MCPToolRequest):
    args = request.arguments
    if request.tool_name == "calculate_pro_rata_premium":
        result = calculate_pro_rata_premium(
            _decimal(args.get("base_premium_inr", "0")),
            date.fromisoformat(args["effective_date"]),
            date.fromisoformat(args["policy_end_date"]),
            date.fromisoformat(args["endorsement_effective_date"]),
            _decimal(args.get("gst_rate_percent", "18")),
            _decimal(args["annual_premium_inr"]) if args.get("annual_premium_inr") is not None else None,
            date.fromisoformat(args["policy_start_date"])
            if args.get("policy_start_date")
            else None,
        )
        result_data = result.model_dump(mode="json")
        result_data["employee_identifier_anonymized"] = args.get(
            "employee_identifier_anonymized", result_data["employee_identifier_anonymized"]
        )
        return {"result": result_data}
    if request.tool_name == "calculate_deletion_credit":
        result = calculate_deletion_credit(
            _decimal(args.get("base_premium_inr", "0")),
            date.fromisoformat(args["cessation_date"]),
            date.fromisoformat(args["policy_end_date"]),
            date.fromisoformat(args["endorsement_effective_date"]),
            _decimal(args.get("gst_rate_percent", "18")),
            _decimal(args["annual_premium_inr"]) if args.get("annual_premium_inr") is not None else None,
            date.fromisoformat(args["policy_start_date"])
            if args.get("policy_start_date")
            else None,
        )
        result_data = result.model_dump(mode="json")
        result_data["employee_identifier_anonymized"] = args.get(
            "employee_identifier_anonymized", result_data["employee_identifier_anonymized"]
        )
        return {"result": result_data}
    if request.tool_name == "calculate_cd_health":
        items = [ProcessedLineItem(**item) for item in args["processed_items"]]
        result = calculate_cd_health(
            _decimal(args["opening_balance_inr"]),
            items,
            _decimal(args["alert_threshold_inr"]),
        )
        return {"result": result.model_dump(mode="json")}
    return {"error": f"Tool '{request.tool_name}' not recognized."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)