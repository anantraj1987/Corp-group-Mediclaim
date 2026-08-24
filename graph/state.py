from typing import List, Dict, Any, TypedDict, Annotated
import operator

class IncidentState(TypedDict):
    """
    Central State Schema for Enterprise Incident Agent Graph.
    Extends Phase 3 state with Mem0 Memory and Redis Caching attributes.
    """
    # User Context
    user_name: str
    user_id: str
    department: str
    raw_query: str
    
    # Mem0 Context Integration
    user_preferences: List[str]  # Loaded from Mem0

    # Security Guardrail Attributes
    guardrail_passed: bool
    guardrail_violation_reason: str

    
    # Classification and Routing Metadata
    intent: str
    sub_category: str
    
    # Context Aggregators
    retrieved_docs: List[Dict[str, Any]]
    telemetry_data: Dict[str, Any]
    code_analysis_data: Dict[str, Any]
    billing_data: Dict[str, Any]
    
    # Solution State
    solution: str
    confidence_score: int
    is_cached_response: bool  # Flag indicating if solution was served from Redis
    
    # Operational Control Attributes
    retry_count: int
    human_approved: bool
    human_feedback: str
    
    # Graph Execution Trace Log
    visited_nodes: Annotated[List[str], operator.add]
    execution_logs: Annotated[List[str], operator.add]

    presidio_token_map: Dict[str, str]  # Holds the secret Token -> Real Value map
