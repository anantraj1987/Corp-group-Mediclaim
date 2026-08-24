from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from config.settings import settings
from schemas.gmc_schemas import (
    CashDepositAccountHealth,
    EndorsementLine,
    PolicyTerms,
    ProcessedLineItem,
    RejectedException,
)
from services.census_ingestion import ingest_csv
from services.docket_assembler import assemble_docket
from services.faiss_service import (
    INDEX_FILE,
    METADATA_FILE,
    build_faiss_index,
    load_faiss_index,
    search_faiss,
)
from services.family_rules import validate_family_members, validate_life_event_window
from services.rag_service import answer_from_retrieved_chunks, find_sla_reference
from services.chunking import process_documents
from services.mcp_client import mcp_remote_client
from services.langsmith_tracing import BatchTrace


class MilestoneDemoService:
    """Coordinates Milestones 1-3 for the local CLI demonstration."""

    def anonymize_identifier(self, identifier: str) -> str:
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8].upper()
        return f"<ANON_EMP_{digest}>"

    def anonymize_corporate_account(self, corporate_account: str) -> str:
        normalized = re.sub(r"\b(India|Pvt|Private|Ltd|Limited)\b", "", corporate_account, flags=re.IGNORECASE)
        token = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").upper()
        return f"<ANON_CORP_{token}>"

    def policy_file_for_corporate(self, corporate_account: str) -> Path:
        requested = re.sub(r"[^a-z0-9]+", "_", corporate_account.lower()).strip("_")
        candidates = sorted(settings.POLICY_DIR.glob("*.txt"))
        for candidate in candidates:
            if requested in candidate.stem.lower():
                return candidate
        available = ", ".join(path.stem for path in candidates)
        raise FileNotFoundError(
            f"No policy SLA file found for '{corporate_account}'. Available files: {available}"
        )

    def load_policy_terms(self, corporate_account: str) -> PolicyTerms:
        policy_file = self.policy_file_for_corporate(corporate_account)
        text = policy_file.read_text(encoding="utf-8")

        tenure = re.search(
            r"Policy Tenure:\s*(\d{2}-\w{3}-\d{4})\s+to\s+(\d{2}-\w{3}-\d{4})",
            text,
        )
        sum_insured = re.search(r"Sum Insured:\s*INR\s*([\d,]+)\s+\((1\+[35])", text)
        life_window = re.search(r"intimated to the TPA within (\d+) days", text, re.IGNORECASE)
        cd_balance = re.search(r"current CD balance is INR\s*([\d,]+\.\d+)", text, re.IGNORECASE)
        threshold = re.search(r"minimum threshold\s+of INR\s*([\d,]+\.\d+)", text, re.IGNORECASE)
        if not all((tenure, sum_insured, life_window, cd_balance, threshold)):
            raise ValueError(f"Could not parse required policy terms from {policy_file.name}")

        parse_policy_date = lambda value: datetime.strptime(value, "%d-%b-%Y").date()
        policy = PolicyTerms(
            corporate_account=corporate_account,
            policy_start_date=parse_policy_date(tenure.group(1)),
            policy_end_date=parse_policy_date(tenure.group(2)),
            sum_insured_inr=Decimal(sum_insured.group(1).replace(",", "")),
            family_definition=sum_insured.group(2),
            life_event_window_days=int(life_window.group(1)),
            cd_balance_inr=Decimal(cd_balance.group(1).replace(",", "")),
            cd_alert_threshold_inr=Decimal(threshold.group(1).replace(",", "")),
        )
        from services.memory_service import mem0_service

        previous_state = mem0_service.history.get_latest_batch(
            corporate_account,
            policy.policy_start_date,
        )
        if previous_state and previous_state.get("closing_cd_balance_inr") is not None:
            try:
                policy.cd_balance_inr = Decimal(
                    str(previous_state["closing_cd_balance_inr"])
                )
            except InvalidOperation:
                pass
        return policy

    def build_policy_index(self, force_rebuild: bool = False):
        if force_rebuild:
            INDEX_FILE.unlink(missing_ok=True)
            METADATA_FILE.unlink(missing_ok=True)

        if INDEX_FILE.exists() and METADATA_FILE.exists():
            existing_index, existing_metadata = load_faiss_index()
            if existing_metadata and all("clause" in item for item in existing_metadata):
                return existing_index, existing_metadata

        documents = [
            {"filename": path.name, "content": path.read_text(encoding="utf-8")}
            for path in settings.POLICY_DIR.glob("*.txt")
        ]
        if not documents:
            return None, []

        chunks, metrics = process_documents(documents)
        index, metadata = build_faiss_index(chunks)
        return index, metadata

    def retrieve_policy(self, query: str, top_k: int = 5, corporate_account: str | None = None):
        index, metadata = self.build_policy_index()
        if index is None:
            raise RuntimeError("No policy index is available. Add policy files and retry.")
        return search_faiss(
            query,
            index,
            metadata,
            top_k=top_k,
            corporate_account=corporate_account,
        )

    def answer_policy_query(
        self,
        query: str,
        top_k: int = 5,
        corporate_account: str | None = None,
        retrieve_only: bool = False,
    ) -> dict:
        evidence = self.retrieve_policy(query, top_k, corporate_account)
        answer = None
        if not retrieve_only and evidence:
            answer, elapsed = answer_from_retrieved_chunks(query, evidence)
        else:
            elapsed = 0.0
        return {"evidence": evidence, "answer": answer, "generation_seconds": elapsed}

    def calculate_with_mcp(
        self,
        lines: list[EndorsementLine],
        policy: PolicyTerms,
        endorsement_effective_date: date,
    ) -> tuple[list[ProcessedLineItem], CashDepositAccountHealth] | None:
        """Calculate endorsement amounts only through the GMC MCP service."""
        processed_items: list[ProcessedLineItem] = []
        for line in lines:
            if line.action_type == "RESIGNATION_DELETION":
                tool_name = "calculate_deletion_credit"
                arguments = {
                    "base_premium_inr": str(line.base_premium_inr),
                    "cessation_date": (
                        line.coverage_cessation_date or endorsement_effective_date
                    ).isoformat(),
                }
            else:
                tool_name = "calculate_pro_rata_premium"
                arguments = {
                    "base_premium_inr": str(line.base_premium_inr),
                    "effective_date": (
                        line.coverage_effective_date or endorsement_effective_date
                    ).isoformat(),
                }
            arguments.update(
                {
                    "employee_identifier_anonymized": line.employee_identifier_anonymized,
                    "policy_end_date": policy.policy_end_date.isoformat(),
                    "endorsement_effective_date": endorsement_effective_date.isoformat(),
                    "gst_rate_percent": str(policy.gst_rate_percent),
                }
            )
            result = mcp_remote_client.call_mcp_service(
                "gmc_actuarial", tool_name, arguments
            )
            if not isinstance(result, dict) or result.get("status") == "fallback":
                return None
            try:
                processed_items.append(ProcessedLineItem(**result))
            except (TypeError, ValueError):
                return None

        health_result = mcp_remote_client.call_mcp_service(
            "gmc_actuarial",
            "calculate_cd_health",
            {
                "opening_balance_inr": str(policy.cd_balance_inr),
                "processed_items": [item.model_dump(mode="json") for item in processed_items],
                "alert_threshold_inr": str(policy.cd_alert_threshold_inr),
            },
        )
        if not isinstance(health_result, dict) or health_result.get("status") == "fallback":
            return None
        try:
            return processed_items, CashDepositAccountHealth(**health_result)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def tbd_calculation_output(
        lines: list[EndorsementLine],
    ) -> tuple[list[ProcessedLineItem], CashDepositAccountHealth]:
        processed_items = [
            ProcessedLineItem(
                employee_identifier_anonymized=line.employee_identifier_anonymized,
                action_type=line.action_type,
                members_covered=line.members_covered,
                members_removed=line.members_removed,
                coverage_effective_date=line.coverage_effective_date,
                coverage_cessation_date=line.coverage_cessation_date,
                status="APPROVED",
                pro_rata_base_premium_inr="TBD",
                gst_18_percent_inr="TBD",
                total_premium_impact_inr="TBD",
            )
            for line in lines
        ]
        return processed_items, CashDepositAccountHealth(
            opening_cd_balance_inr="TBD",
            net_premium_adjustment_inr="TBD",
            closing_cd_balance_inr="TBD",
            cd_replenishment_alert="TBD",
        )

    def run_census_demo(
        self,
        census_path: Path,
        corporate_account: str,
        endorsement_effective_date: date,
        policy_query: str,
        top_k: int = 5,
        retrieve_only: bool = True,
        force_rebuild: bool = False,
    ) -> dict:
        ingestion = ingest_csv(census_path)
        policy = self.load_policy_terms(corporate_account)
        source_digest = hashlib.sha256(census_path.read_bytes()).hexdigest()
        records = [
            record for record in ingestion.records
            if record.corporate_account
            and record.corporate_account.lower() == corporate_account.lower()
        ]
        if not records:
            raise ValueError(f"No valid census records found for '{corporate_account}'.")

        batch_id = hashlib.sha256(
            f"{corporate_account}|{policy.policy_start_date.isoformat()}|{source_digest}".encode("utf-8")
        ).hexdigest()
        trace = BatchTrace(
            batch_id=batch_id,
            corporate_account=self.anonymize_corporate_account(corporate_account),
            policy_start=policy.policy_start_date.isoformat(),
        )

        if force_rebuild:
            self.build_policy_index(force_rebuild=True)
        with trace.stage("policy_retrieval", {"top_k": top_k}):
            rag_result = self.answer_policy_query(
                policy_query,
                top_k=top_k,
                corporate_account=corporate_account,
                retrieve_only=retrieve_only,
            )
        life_event_sla_reference = find_sla_reference(
            rag_result["evidence"], "life event"
        )
        with trace.stage("family_policy_retrieval", {"top_k": top_k}):
            family_result = self.answer_policy_query(
                "What family definition and dependent cross-selection rules apply?",
                top_k=top_k,
                corporate_account=corporate_account,
                retrieve_only=True,
            )
        family_sla_reference = find_sla_reference(
            family_result["evidence"], "family definition"
        )

        approved_lines: list[EndorsementLine] = []
        rejected_exceptions = []
        with trace.stage("deterministic_validation", {"record_count": len(records)}):
            for record in records:
                anonymized_id = self.anonymize_identifier(record.employee_identifier)
                if record.action_type != "RESIGNATION_DELETION":
                    rejected_exceptions.extend(
                        validate_family_members(
                            anonymized_id,
                            record.members,
                            policy,
                            action_type=record.action_type,
                            sla_reference=family_sla_reference,
                        )
                    )
                if record.action_type == "LIFE_EVENT_ADDITION":
                    if record.event_date is None or record.intimation_date is None:
                        rejected_exceptions.append(
                            RejectedException(
                                employee_identifier_anonymized=anonymized_id,
                                attempted_action=record.action_type,
                                rejection_reason=(
                                    "Life-event additions require both event_date and "
                                    f"intimation_date to verify the {policy.life_event_window_days}-day window."
                                ),
                                sla_reference=life_event_sla_reference,
                            )
                        )
                    else:
                        exception = validate_life_event_window(
                            anonymized_id,
                            record.action_type,
                            record.event_date,
                            record.intimation_date,
                            policy,
                            sla_reference=life_event_sla_reference,
                        )
                        if exception:
                            rejected_exceptions.append(exception)

                has_exception = any(
                    exception.employee_identifier_anonymized == anonymized_id
                    for exception in rejected_exceptions
                )
                if not has_exception:
                    approved_lines.append(
                        EndorsementLine(
                            employee_identifier_anonymized=anonymized_id,
                            action_type=record.action_type,
                            members_covered=record.members,
                            members_removed=(
                                record.members
                                if record.action_type == "RESIGNATION_DELETION"
                                else []
                            ),
                            coverage_effective_date=record.coverage_effective_date,
                            coverage_cessation_date=record.coverage_cessation_date,
                            event_date=record.event_date,
                            intimation_date=record.intimation_date,
                            base_premium_inr=record.base_premium_inr,
                        )
                    )

        with trace.stage("mcp_actuarial_calculation", {"approved_count": len(approved_lines)}):
            mcp_calculation = self.calculate_with_mcp(
                approved_lines,
                policy,
                endorsement_effective_date,
            )
        if mcp_calculation is None:
            processed_items, account_health = self.tbd_calculation_output(approved_lines)
        else:
            processed_items, account_health = mcp_calculation

        with trace.stage("docket_assembly", {"exception_count": len(rejected_exceptions)}):
            docket = assemble_docket(
                endorsement_id=(
                    f"END-{endorsement_effective_date:%Y%m%d}-"
                    f"{hashlib.sha1(corporate_account.encode()).hexdigest()[:8].upper()}"
                ),
                endorsement_effective_date=endorsement_effective_date,
                policy=policy,
                approved_lines=approved_lines,
                rejected_exceptions=rejected_exceptions,
                processed_items=processed_items,
                account_health=account_health,
            )

        with trace.stage("mem0_persistence", {"batch_id": batch_id}):
            history_status = self.record_history(
                census_path=census_path,
                source_digest=source_digest,
                corporate_account=corporate_account,
                policy=policy,
                endorsement_effective_date=endorsement_effective_date,
                records=records,
                approved_count=len(approved_lines),
                exception_count=len(rejected_exceptions),
                docket=docket,
                rejected_exceptions=rejected_exceptions,
            )

        memory_status = self.record_memory(
            corporate_account,
            endorsement_effective_date,
            len(approved_lines),
            len(rejected_exceptions),
        )

        output = docket.model_dump(mode="json")
        output["corporate_account"] = self.anonymize_corporate_account(corporate_account)
        output["policy_evidence"] = [
            {
                "source": item["filename"],
                "clause": item.get("clause", "Unspecified"),
                "citation": f"[Source: {item['filename']} | Clause: {item.get('clause', 'Unspecified')}]",
            }
            for item in rag_result["evidence"]
        ]
        trace.finish(
            "completed",
            approved_count=len(approved_lines),
            exception_count=len(rejected_exceptions),
            guardrails_status=docket.guardrails_validation_status,
        )
        return output

    def record_history(
        self,
        census_path: Path,
        source_digest: str,
        corporate_account: str,
        policy: PolicyTerms,
        endorsement_effective_date: date,
        records: list,
        approved_count: int,
        exception_count: int,
        docket,
        rejected_exceptions: list,
    ) -> str:
        from services.memory_service import mem0_service

        batch_id = mem0_service.history.batch_id(
            corporate_account,
            policy.policy_start_date,
            source_digest,
        )
        record = {
            "corporate_account": corporate_account,
            "policy_term_id": (
                f"{corporate_account}|{policy.policy_start_date.isoformat()}|"
                f"{policy.policy_end_date.isoformat()}"
            ),
            "policy_start_date": policy.policy_start_date.isoformat(),
            "endorsement_effective_date": endorsement_effective_date.isoformat(),
            "source_file": census_path.name,
            "approved_count": approved_count,
            "exception_count": exception_count,
            "policy_counters": {
                "additions_processed": docket.endorsement_summary.additions_processed,
                "deletions_processed": docket.endorsement_summary.deletions_processed,
                "exceptions_flagged": docket.endorsement_summary.exceptions_flagged,
                "monthly_census_changes": len(records),
            },
            "life_event_window_days": policy.life_event_window_days,
            "opening_cd_balance_inr": str(docket.cash_deposit_account_health.opening_cd_balance_inr),
            "net_premium_adjustment_inr": str(docket.cash_deposit_account_health.net_premium_adjustment_inr),
            "closing_cd_balance_inr": str(docket.cash_deposit_account_health.closing_cd_balance_inr),
            "cd_replenishment_alert": docket.cash_deposit_account_health.cd_replenishment_alert,
        }
        record["state_user_id"] = mem0_service.history._state_user_id(
            record["corporate_account"], policy.policy_start_date
        )
        inserted = mem0_service.history.record_batch(batch_id, record)
        for item in records:
            employee_token = item.employee_identifier
            exception = next(
                (
                    value for value in rejected_exceptions
                    if value.employee_identifier_anonymized == self.anonymize_identifier(item.employee_identifier)
                ),
                None,
            )
            mem0_service.history.record_enrollment(
                employee_token,
                policy.policy_start_date.isoformat(),
                item.members,
                {
                    "corporate_account": corporate_account,
                    "policy_term_id": record["policy_term_id"],
                    "batch_id": batch_id,
                    "action_type": item.action_type,
                    "event_date": item.event_date.isoformat() if item.event_date else None,
                    "intimation_date": item.intimation_date.isoformat() if item.intimation_date else None,
                    "decision": "REJECTED" if exception else "APPROVED",
                    "rejection_reason": exception.rejection_reason if exception else None,
                    "sla_reference": exception.sla_reference if exception else None,
                },
            )
        return "RECORDED" if inserted else "DUPLICATE"

    def record_memory(
        self,
        corporate_account: str,
        endorsement_effective_date: date,
        approved_count: int,
        exception_count: int,
    ) -> str:
        try:
            from services.memory_service import mem0_service

            if mem0_service.memory is None:
                raise RuntimeError("Mem0 memory backend is unavailable")
            memory_user_id = re.sub(
                r"[^A-Za-z0-9_.:-]+",
                "_",
                f"corporate:{corporate_account}",
            )
            mem0_service.add_user_memory(
                memory_user_id,
                f"Processed census batch for {corporate_account} on {endorsement_effective_date.isoformat()}: "
                f"{approved_count} approved lines and {exception_count} exceptions.",
            )
            return "RECORDED"
        except Exception as error:
            return f"UNAVAILABLE: {type(error).__name__}"
