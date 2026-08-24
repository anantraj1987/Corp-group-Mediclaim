from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from app import (
    DEFAULT_CORPORATE,
    add_inline_employee_fields,
    anonymize_employee_fields,
    build_display_token_map,
    rehydrate_for_display,
    save_docket,
    service,
)
from config.settings import settings
from services.rag_service import answer_policy_query


ROOT_DIR = Path(__file__).resolve().parent
CENSUS_DIR = ROOT_DIR / "data" / "census"

st.set_page_config(
    page_title="GMC Endorsement Desk",
    page_icon="+",
    layout="wide",
    initial_sidebar_state="expanded",
)


def start_mcp_server() -> None:
    process = st.session_state.get("mcp_process")
    if process and process.poll() is None:
        return
    st.session_state["mcp_process"] = subprocess.Popen(
        [sys.executable, "-m", "mcp_services.gmc_actuarial_service"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def stop_mcp_server() -> None:
    process = st.session_state.get("mcp_process")
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    st.session_state["mcp_process"] = None


def mcp_is_running() -> bool:
    process = st.session_state.get("mcp_process")
    return bool(process and process.poll() is None)


def selected_census_path(uploaded_file, selected_file: str) -> Path:
    if uploaded_file is None:
        return CENSUS_DIR / selected_file
    temporary_file = tempfile.NamedTemporaryFile(
        suffix=Path(uploaded_file.name).suffix or ".csv", delete=False
    )
    temporary_file.write(uploaded_file.getvalue())
    temporary_file.close()
    return Path(temporary_file.name)


def run_census_workflow(
    census_path: Path, corporate: str, query: str, effective_date: str
) -> tuple[dict, dict[str, str]]:
    result = service.run_census_demo(
        census_path=census_path,
        corporate_account=corporate,
        endorsement_effective_date=date.fromisoformat(effective_date),
        policy_query=query,
        retrieve_only=True,
    )
    token_map = build_display_token_map(census_path, corporate)
    add_inline_employee_fields(result, anonymize_employee_fields(census_path, token_map))
    return result, token_map


with st.sidebar:
    st.markdown("## GMC control room")
    st.caption("One local actuarial MCP server powers premium and CD calculations.")
    if mcp_is_running():
        st.success("MCP server running · 127.0.0.1:8001")
        if st.button("Stop MCP server", use_container_width=True):
            stop_mcp_server()
            st.rerun()
    else:
        st.warning("MCP server offline · actuarial fields return TBD")
        if st.button("Start MCP server", type="primary", use_container_width=True):
            start_mcp_server()
            st.rerun()

    st.divider()
    st.markdown("### LangSmith")
    tracing_enabled = st.toggle(
        "Enable tracing",
        value=os.environ.get("LANGCHAIN_TRACING_V2", settings.LANGCHAIN_TRACING_V2).lower() == "true",
    )
    project_name = st.text_input(
        "Project",
        value=os.environ.get("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT),
    ).strip() or settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_enabled else "false"
    os.environ["LANGCHAIN_PROJECT"] = project_name
    st.caption(f"Tracing {'enabled' if tracing_enabled else 'disabled'} · {project_name}")
    st.caption("API key: configured" if settings.LANGCHAIN_API_KEY else "API key: not configured")


st.title("Corporate GMC Endorsement Desk")
st.caption("Review monthly census changes, contract-backed policy answers, and insurer-ready endorsement JSON.")

census_tab, policy_tab = st.tabs(["HR census review", "Policy information"])

with census_tab:
    st.subheader("Monthly census intake")
    left, right = st.columns([1.4, 1])
    census_files = sorted(path.name for path in CENSUS_DIR.glob("*.csv"))
    selected_file = left.selectbox(
        "Census file",
        census_files,
        index=census_files.index("techcorp_july_2026_validation_demo.csv")
        if "techcorp_july_2026_validation_demo.csv" in census_files
        else 0,
    )
    uploaded_file = left.file_uploader("Or upload a CSV", type=["csv"], accept_multiple_files=False)
    corporate = right.text_input("Corporate account", value=DEFAULT_CORPORATE)
    effective_date = right.date_input("Endorsement effective date", value=date(2026, 7, 1))
    policy_query = st.text_input(
        "SLA question for this batch",
        value="What family and life-event rules apply?",
    )

    if st.button("Process census and create JSON", type="primary", use_container_width=True):
        source_path = selected_census_path(uploaded_file, selected_file)
        try:
            with st.spinner("Ingesting, retrieving SLA evidence, calling MCP, and persisting Mem0 state..."):
                result, token_map = run_census_workflow(
                    source_path, corporate, policy_query, effective_date.isoformat()
                )
                saved_path = save_docket(result, ROOT_DIR / "output")
            st.session_state["census_result"] = result
            st.session_state["census_display"] = rehydrate_for_display(result, token_map)
            st.session_state["census_saved_path"] = str(saved_path)
            st.success(f"JSON saved to {saved_path}")
        except Exception as error:
            st.error(f"Census processing failed: {error}")

    if "census_result" in st.session_state:
        result = st.session_state["census_result"]
        display_result = st.session_state["census_display"]
        summary = result["endorsement_summary"]
        metrics = st.columns(4)
        metrics[0].metric("Additions", summary["additions_processed"])
        metrics[1].metric("Deletions", summary["deletions_processed"])
        metrics[2].metric("Exceptions", summary["exceptions_flagged"])
        metrics[3].metric("Guardrails", result["guardrails_validation_status"])
        st.caption(f"Saved anonymized JSON: {st.session_state['census_saved_path']}")
        anonymized_tab, rehydrated_tab = st.tabs(["Anonymized JSON", "Rehydrated CLI-style view"])
        with anonymized_tab:
            st.json(result)
            st.download_button(
                "Download anonymized JSON",
                json.dumps(result, indent=2),
                file_name=Path(st.session_state["census_saved_path"]).name,
                mime="application/json",
            )
        with rehydrated_tab:
            st.json(display_result)

with policy_tab:
    st.subheader("Contract-backed policy search")
    policy_corporate = st.text_input("Corporate account", value=DEFAULT_CORPORATE, key="policy_corporate")
    policy_question = st.text_area(
        "Coverage question",
        value="What is the life-event intimation window and family definition?",
        height=110,
    )
    policy_top_k = st.slider("Evidence clauses", min_value=1, max_value=10, value=5)
    if st.button("Search policy", type="primary"):
        try:
            with st.spinner("Retrieving corporate SLA evidence..."):
                answer, evidence, retrieval_seconds, generation_seconds = answer_policy_query(
                    user_query=policy_question,
                    user_info={"role": "HR team", "dept": policy_corporate},
                    corporate_account=policy_corporate,
                    top_k=policy_top_k,
                )
            st.session_state["policy_result"] = {
                "answer": answer,
                "evidence": evidence,
                "retrieval_seconds": retrieval_seconds,
                "generation_seconds": generation_seconds,
            }
        except Exception as error:
            st.error(f"Policy search failed: {error}")

    if "policy_result" in st.session_state:
        policy_result = st.session_state["policy_result"]
        st.markdown("### Answer")
        st.write(policy_result["answer"])
        st.caption(
            f"Retrieval: {policy_result['retrieval_seconds']}s · "
            f"Generation: {policy_result['generation_seconds']}s"
        )
        st.markdown("### Retrieved SLA evidence")
        for index, item in enumerate(policy_result["evidence"], start=1):
            filename = item.get("filename") or item.get("file", "Unknown")
            citation = f"[Source: {filename} | Clause: {item.get('clause', 'Unspecified')}]"
            with st.expander(f"{index}. {citation}"):
                st.write(item.get("content", ""))
