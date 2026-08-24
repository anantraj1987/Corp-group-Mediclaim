#Wires input_guardrail_node as the ENTRY POINT and output_guardrail_node right before END.

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import IncidentState
from graph.router import route_by_intent, evaluate_confidence_route

# Import Nodes
from nodes.guardrail_node_old import input_guardrail_node, output_guardrail_node
from nodes.classify_node import classify_intent_node
from nodes.auth_node import auth_analysis_node
from nodes.mcp_node import mcp_execution_node
from nodes.kb_node import fallback_kb_node
from nodes.solution_node import generate_solution_node
from nodes.confidence_node import confidence_check_node
from nodes.human_node import human_approval_node


def route_guardrail_check(state: IncidentState) -> str:
    """Conditional Edge: Routes to Intent Classifier if guardrail passes, else exits immediately."""
    if state.get("guardrail_passed", True):
        return "classify_node"
    return "END"


def build_guarded_mcp_graph(checkpointer=None) -> StateGraph:
    """Constructs StateGraph wrapped with Security Guardrail Nodes."""
    workflow = StateGraph(IncidentState)

    # 1. Register All Nodes
    workflow.add_node("input_guardrail_node", input_guardrail_node)
    workflow.add_node("classify_node", classify_intent_node)
    workflow.add_node("auth_node", auth_analysis_node)
    workflow.add_node("mcp_execution_node", mcp_execution_node)
    workflow.add_node("kb_node", fallback_kb_node)
    workflow.add_node("solution_node", generate_solution_node)
    workflow.add_node("confidence_node", confidence_check_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("output_guardrail_node", output_guardrail_node)

    # 2. ENTRY POINT is now the Input Guardrail Node!
    workflow.set_entry_point("input_guardrail_node")

    # 3. Guardrail Conditional Routing Edge
    workflow.add_conditional_edges(
        "input_guardrail_node",
        route_guardrail_check,
        {
            "classify_node": "classify_node",
            "END": END,
        }
    )

    # 4. Intent Classification Routing Edge
    workflow.add_conditional_edges(
        "classify_node",
        route_by_intent,
        {
            "auth_node": "auth_node",
            "monitoring_node": "mcp_execution_node",
            "code_node": "mcp_execution_node",
            "billing_node": "mcp_execution_node",
            "kb_node": "kb_node",
        },
    )

    # Domain / MCP Nodes -> Solution Generator
    workflow.add_edge("auth_node", "solution_node")
    workflow.add_edge("mcp_execution_node", "solution_node")
    workflow.add_edge("kb_node", "solution_node")

    # Solution -> Confidence Evaluation
    workflow.add_edge("solution_node", "confidence_node")

    # 5. Confidence Check Edge -> Output Guardrail -> END
    workflow.add_conditional_edges(
        "confidence_node",
        evaluate_confidence_route,
        {
            "END": "output_guardrail_node",  # Routes through Output Sanitizer before completion
            "solution_node": "solution_node",
            "human_approval_node": "human_approval_node",
        },
    )

    workflow.add_conditional_edges(
        "human_approval_node",
        lambda state: "output_guardrail_node" if state.get("human_approved") else "solution_node",
        {
            "output_guardrail_node": "output_guardrail_node",
            "solution_node": "solution_node"
        }
    )

    # Output Guardrail -> END
    workflow.add_edge("output_guardrail_node", END)

    memory_saver = checkpointer if checkpointer is not None else MemorySaver()
    return workflow.compile(checkpointer=memory_saver)


compiled_guarded_graph = build_guarded_mcp_graph()
