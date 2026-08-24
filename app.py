from __future__ import annotations

import argparse
import csv
import json
import hashlib
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from config.settings import settings
from presidio_governance.anonymizer import presidio_anonymizer_service
from presidio_governance.rehydrator import presidio_rehydrator_service
from services.census_ingestion import ingest_csv
from services.milestone_demo_service import MilestoneDemoService
from services.rag_service import answer_policy_query as rag_answer_policy_query


console = Console()
service = MilestoneDemoService()
DEFAULT_CENSUS_PATH = Path("data/census/techcorp_july_2026_demo.csv")
DEFAULT_CORPORATE = "TechCorp India Pvt Ltd"
DEFAULT_OUTPUT_DIR = Path("output")


def print_banner() -> None:
    console.clear()
    console.print(
        Panel.fit(
            f"[bold cyan]{settings.PROJECT_NAME}[/bold cyan] "
            "[bold green](Milestones 1-3 CLI Demo)[/bold green]\n"
            "[dim]Census privacy • Corporate policy RAG • Calculations and memory[/dim]",
            border_style="cyan",
        )
    )


def print_policy_result(result: dict) -> None:
    evidence = result["evidence"]
    if not evidence:
        console.print("[yellow]No matching corporate SLA evidence was retrieved.[/yellow]")
        return

    console.print(f"\n[bold blue]Retrieved {len(evidence)} contract clause(s):[/bold blue]")
    for number, item in enumerate(evidence, start=1):
        filename = item.get("filename") or item.get("file", "Unknown")
        citation = f"{filename} | {item.get('clause', 'Unspecified')}"
        console.print(
            f"\n[bold]{number}. {citation}[/bold] "
            f"[dim](score={item['score']:.3f})[/dim]"
        )
        console.print(item["content"])

    if result["answer"]:
        console.print("\n[bold green]Contract-grounded answer[/bold green]")
        console.print(result["answer"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Corporate GMC HR census and policy information CLI"
    )
    parser.add_argument("--query", help="Corporate policy question")
    parser.add_argument(
        "--census",
        type=Path,
        help="Monthly census CSV for the HR endorsement review workflow",
    )
    parser.add_argument(
        "--effective-date",
        default="2026-07-01",
        help="Endorsement effective date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of policy chunks to retrieve",
    )
    parser.add_argument(
        "--corporate",
        help="Corporate account whose SLA should be used",
    )
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="Retrieve policy evidence without calling the LLM",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the local FAISS policy index",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated endorsement JSON files",
    )
    parser.add_argument(
        "--option",
        choices=["1", "2"],
        help="Run an activity directly: 1 HR census review, 2 policy information",
    )
    return parser.parse_args()


def save_docket(result: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{result['endorsement_id']}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return output_path


def build_display_token_map(census_path: Path, corporate: str) -> dict[str, str]:
    """Create the in-memory Presidio map used only for authorized CLI display."""
    raw_census = census_path.read_text(encoding="utf-8-sig")
    _, token_map = presidio_anonymizer_service.anonymize_and_map(raw_census)

    # The docket service uses stable short tokens for its public fields. Alias
    # those tokens to the same raw values without persisting the raw map.
    rows = csv.DictReader(raw_census.splitlines())
    for row in rows:
        employee_identifier = (
            row.get("employee_id")
            or row.get("employee_identifier")
            or row.get("emp_id")
            or ""
        ).strip()
        if employee_identifier:
            token_map[
                f"<ANON_EMP_{hashlib.sha256(employee_identifier.encode('utf-8')).hexdigest()[:8].upper()}>"
            ] = employee_identifier

    token_map[service.anonymize_corporate_account(corporate)] = corporate
    return token_map


def rehydrate_for_display(result: dict, token_map: dict[str, str]) -> dict:
    """Rehydrate a copy of the saved JSON; never mutate the persisted result."""
    serialized = json.dumps(result)
    rehydrated = presidio_rehydrator_service.rehydrate_text(serialized, token_map)
    return json.loads(rehydrated)


def anonymize_employee_fields(census_path: Path, token_map: dict[str, str]) -> dict[str, dict[str, str | None]]:
    """Create anonymized inline employee fields for the persisted docket."""
    raw_census = census_path.read_text(encoding="utf-8-sig")
    details = {}
    for row in csv.DictReader(raw_census.splitlines()):
        fields = {
            "employee_identifier": row.get("employee_id") or row.get("employee_identifier") or "",
            "email": row.get("work_email") or row.get("corporate_email") or "",
            "dob": row.get("dob") or row.get("date_of_birth") or "",
            "aadhaar": row.get("aadhaar") or row.get("aadhaar_number") or "",
        }
        anonymized = {}
        for name, value in fields.items():
            if not value:
                anonymized[name] = None
                continue
            if name == "employee_identifier":
                token = f"<ANON_EMP_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8].upper()}>"
                token_map[token] = value
            else:
                token, _ = presidio_anonymizer_service.anonymize_and_map(value, token_map)
            anonymized[name] = token
        employee_token = anonymized["employee_identifier"]
        if employee_token:
            details[employee_token] = {
                "email": anonymized["email"],
                "dob": anonymized["dob"],
                "aadhaar": anonymized["aadhaar"],
            }
    return details


def add_inline_employee_fields(result: dict, employee_fields: dict) -> None:
    """Attach PII fields to each employee record without a separate details array."""
    for collection_name in ("processed_line_items", "rejected_exceptions"):
        for item in result.get(collection_name, []):
            fields = employee_fields.get(item.get("employee_identifier_anonymized"))
            if fields:
                item.update(fields)


def run_census_cli(args: argparse.Namespace, census_path: Path, corporate: str) -> None:
    display_token_map = build_display_token_map(census_path, corporate)
    result = service.run_census_demo(
        census_path=census_path,
        corporate_account=corporate,
        endorsement_effective_date=date.fromisoformat(args.effective_date),
        policy_query=args.query or "What family and life-event rules apply?",
        top_k=args.top_k,
        retrieve_only=args.retrieve_only,
        force_rebuild=args.rebuild,
    )
    add_inline_employee_fields(
        result, anonymize_employee_fields(census_path, display_token_map)
    )
    output_path = save_docket(result, args.output_dir)
    console.print(f"\n[green]Endorsement JSON saved to:[/green] {output_path}")
    display_result = rehydrate_for_display(result, display_token_map)
    rejected_rows = display_result.get("rejected_exceptions", [])
    console.print(
        f"\n[bold red]Rejected endorsement rows: {len(rejected_rows)}[/bold red]"
    )
    for rejected_row in rejected_rows:
        console.print(
            f"- {rejected_row['employee_identifier_anonymized']}: "
            f"{rejected_row['rejection_reason']}"
        )
    console.print("\n[bold yellow]Rehydrated CLI display (saved JSON remains anonymized)[/bold yellow]")
    console.print_json(json.dumps(display_result))


def run_privacy_census_cli(args: argparse.Namespace) -> None:
    census_input = (
        str(args.census)
        if args.census
        else Prompt.ask(
            "\n[bold]Census file[/bold]",
            default=str(DEFAULT_CENSUS_PATH),
        )
    ).strip()
    corporate = (
        args.corporate
        or Prompt.ask(
            "[bold]Corporate account[/bold]",
            default=DEFAULT_CORPORATE,
        )
    ).strip()

    ingestion = ingest_csv(Path(census_input))
    console.print(
        f"\n[bold green]Milestone 1: Census ingested and anonymized[/bold green]"
        f"\nValid records: {len(ingestion.records)}"
        f"\nCSV validation errors: {len(ingestion.row_errors)}"
    )
    if ingestion.row_errors:
        console.print("\n[bold red]Row validation errors[/bold red]")
        for error in ingestion.row_errors:
            console.print(f"Row {error['row']}: {error['error']}")

    if not ingestion.records:
        return

    # Option 1 is the HR review workflow: run the complete pipeline after the
    # upload, then save the anonymized endorsement docket as JSON.
    run_census_cli(args, Path(census_input), corporate)


def run_policy_rag_cli(args: argparse.Namespace) -> None:
    corporate = (
        args.corporate
        or Prompt.ask(
            "\n[bold]Corporate account[/bold]",
            default=DEFAULT_CORPORATE,
        )
    ).strip()
    query = (
        args.query
        or Prompt.ask(
            "[bold]Coverage query[/bold]",
            default="What family and life-event rules apply?",
        )
    ).strip()
    answer, evidence, retrieval_seconds, generation_seconds = rag_answer_policy_query(
        user_query=query,
        user_info={"role": "HR team", "dept": corporate},
        corporate_account=corporate,
        top_k=args.top_k,
    )
    print_policy_result(
        {
            "answer": answer if not args.retrieve_only else None,
            "evidence": evidence,
            "retrieval_seconds": retrieval_seconds,
            "generation_seconds": generation_seconds if not args.retrieve_only else 0.0,
        }
    )


def run_selected_option(args: argparse.Namespace, option: str) -> None:
    if option == "1":
        run_privacy_census_cli(args)
    else:
        run_policy_rag_cli(args)


def run_interactive_session(args: argparse.Namespace) -> None:
    while True:
        console.print("\n[dim][1] HR Census Review  [2] Policy Information  [q] Exit[/dim]")
        option = Prompt.ask(
            "\n[bold]Choose activity[/bold]",
            choices=["1", "2", "q"],
            default="1",
            show_choices=False,
        )
        if option == "q":
            console.print("\n[dim]Session closed.[/dim]")
            return
        run_selected_option(args, option)


def main() -> None:
    args = parse_args()
    print_banner()

    if args.option:
        run_selected_option(args, args.option)
        return

    if args.census:
        if not args.corporate:
            raise SystemExit("--census requires --corporate")
        run_census_cli(args, args.census, args.corporate)
        return

    if args.rebuild:
        service.build_policy_index(force_rebuild=True)

    if not args.query and not args.retrieve_only:
        run_interactive_session(args)
        return

    if args.query:
        result = service.answer_policy_query(
            query=args.query,
            top_k=args.top_k,
            corporate_account=args.corporate,
            retrieve_only=args.retrieve_only,
        )
        print_policy_result(result)
    else:
        service.build_policy_index()
        console.print("\n[dim]Use --query to retrieve corporate policy evidence.[/dim]")


if __name__ == "__main__":
    main()
