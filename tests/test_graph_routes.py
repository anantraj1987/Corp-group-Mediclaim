import pytest
from graph.graph_builder import build_incident_graph
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture
def graph():
    """Provides a fresh compiled graph with memory checkpointer."""
    return build_incident_graph(checkpointer=MemorySaver())


def test_password_routing_path(graph):
    """Verify password queries route strictly through Auth Node."""
    initial_state = {
        "user_name": "TestUser",
        "department": "IT",
        "raw_query": "Forgot my Outlook password",
        "visited_nodes": ["START"]
    }
    config = {"configurable": {"thread_id": "test_auth_01"}}
    
    result = graph.invoke(initial_state, config=config)
    
    assert result["intent"] == "Authentication"
    assert "auth_node" in result["visited_nodes"]
    assert "monitoring_node" not in result["visited_nodes"]
    assert "billing_node" not in result["visited_nodes"]


def test_infrastructure_routing_path(graph):
    """Verify infrastructure queries route to Monitoring and KB nodes."""
    initial_state = {
        "user_name": "OpsUser",
        "department": "DevOps",
        "raw_query": "EC2 CPU is at 99%",
        "visited_nodes": ["START"]
    }
    config = {"configurable": {"thread_id": "test_infra_01"}}
    
    result = graph.invoke(initial_state, config=config)
    
    assert result["intent"] == "Infrastructure"
    assert "monitoring_node" in result["visited_nodes"]
    assert "code_node" not in result["visited_nodes"]


if __name__ == "__main__":
    pytest.main(["-v", __file__])
