from rich.console import Console
from rich.panel import Panel
from graph.graph_builder import compiled_graph

console = Console()


def export_mermaid_diagram():
    """Generates Mermaid syntax for visual graph rendering."""
    try:
        mermaid_syntax = compiled_graph.get_graph().to_mermaid()
        console.print(Panel(mermaid_syntax, title="Mermaid Graph Representation", border_style="cyan"))
        
        # Save to file
        with open("graph_diagram.mmd", "w") as f:
            f.write(mermaid_syntax)
        console.print("[green]Exported graph structure to 'graph_diagram.mmd'. You can render this in Mermaid Live Editor.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to generate diagram: {str(e)}[/red]")


if __name__ == "__main__":
    export_mermaid_diagram()
