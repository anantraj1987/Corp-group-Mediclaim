from rich.console import Console
from rich.prompt import Prompt
from graph.state import IncidentState
from utils.logger import logger

console = Console()

def human_approval_node(state: IncidentState) -> dict:
    """Node: Pauses execution for human intervention when confidence is below threshold."""
    logger.info("--- [NODE] Human Approval Escalation ---")
    
    console.print("\n[bold red]⚠️ LOW CONFIDENCE DETECTED — ESCALATING TO HUMAN APPROVER[/bold red]")
    console.print(f"Current Confidence: [yellow]{state.get('confidence_score')}%[/yellow]")
    console.print(f"Proposed Solution Preview:\n[dim]{state.get('solution')[:300]}...[/dim]\n")
    
    choice = Prompt.ask(
        "Choose Action",
        choices=["1", "2", "3"],
        default="1",
        show_choices=False,
        description="[1] Approve Solution  [2] Provide Feedback & Regenerate  [3] Escalate to Tier 3"
    )
    
    if choice == "1":
        return {
            "human_approved": True,
            "visited_nodes": ["human_approval_node"],
            "execution_logs": ["Approved by Tier-2 Operator"]
        }
    elif choice == "2":
        feedback = Prompt.ask("Enter detailed operational feedback for agent loop")
        return {
            "human_approved": False,
            "human_feedback": feedback,
            "visited_nodes": ["human_approval_node"],
            "execution_logs": [f"Human feedback recorded: {feedback}"]
        }
    else:
        return {
            "human_approved": True,
            "solution": "ESCALATED TO TIER-3 HUMAN ENGINEERING TEAM. Ticket #INC-99201 Created.",
            "visited_nodes": ["human_approval_node"],
            "execution_logs": ["Ticket escalated to Tier-3 human engineering"]
        }
