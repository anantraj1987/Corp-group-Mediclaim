# Project Flow

This project reviews monthly corporate Group Mediclaim (GMC) census changes and
creates an anonymized endorsement JSON docket.

## High-Level Flow

```text
User / HR upload
      |
      v
app.py or streamlit_app.py
      |
      v
MilestoneDemoService.run_census_demo()
      |
      +--> ingest_csv() --------------------> validated CensusMember records
      |
      +--> load_policy_terms() -------------> PolicyTerms from corporate SLA
      |
      +--> answer_policy_query() ------------> SLA evidence and citations
      |       |
      |       +--> build_policy_index() ------> clause chunks + FAISS index
      |       +--> retrieve_policy() ---------> corporate-filtered clauses
      |
      +--> validate_family_members() --------> family-rule exceptions
      +--> validate_life_event_window() -----> life-event exceptions
      |
      +--> calculate_with_mcp() -------------> premiums, GST, deletion credit,
      |                                         and CD account health
      |
      +--> assemble_docket() ---------------> Pydantic endorsement docket
      |       |
      |       +--> validate_endorsement_docket() -> PASS / FAILED
      |
      +--> record_history() / record_memory() -> local audit and memory state
      |
      v
Anonymized JSON saved under output/
```

## Entry Points

| File / method | Responsibility |
| --- | --- |
| `app.py` | Command-line entry point. Accepts a census file or policy question, displays results, saves JSON, and rehydrates a copy only for authorized CLI display. |
| `streamlit_app.py` | Web UI entry point. Runs the census review and policy-search workflows and displays/downloads the results. |
| `run_census_workflow()` | Streamlit adapter that calls the shared batch service and adds anonymized employee fields for display. |
| `MilestoneDemoService.run_census_demo()` | Main orchestration method for the complete census endorsement flow. |

## Processing Methods

| Method | What it does |
| --- | --- |
| `ingest_csv()` | Reads the CSV, normalizes header aliases, parses dates/members/amounts, validates rows with Pydantic, and reports row-level errors. |
| `load_policy_terms()` | Finds the corporate SLA file, extracts policy dates, family definition, life-event window, sum insured, and CD settings. It also reads the latest saved CD balance when available. |
| `build_policy_index()` | Builds or loads the local FAISS policy index from clause-aware policy chunks. |
| `retrieve_policy()` | Searches policy clauses, optionally filtered by corporate account. |
| `answer_policy_query()` | Retrieves clauses and, when enabled, asks the LLM to produce an answer grounded in those clauses. |
| `find_sla_reference()` | Converts matching retrieved evidence into an exact source and clause citation for exceptions. |
| `validate_family_members()` | Checks duplicate members, parent/parent-in-law cross-selection, dependent limits, and child limits. |
| `validate_life_event_window()` | Checks that intimation is not before the event and is within the policy day limit. |
| `calculate_with_mcp()` | Sends approved lines to the actuarial MCP service and converts returned values into typed Pydantic objects. Uses `tbd_calculation_output()` if the service is unavailable. |
| `calculate_line_item()` | Calculates pro-rata premium/GST for additions or deletion credit for resignations using `Decimal` and two-decimal rounding. |
| `calculate_account_health()` | Reconciles the net premium adjustment with the opening and closing cash-deposit balance and blocks overdrafts. |
| `assemble_docket()` | Creates the final `EndorsementDocket`, counts additions/deletions/exceptions, and sets the guardrail status. |
| `validate_endorsement_docket()` | Checks anonymization, available calculations, CD reconciliation, non-negative balance, and summary counts. |
| `record_history()` | Stores an idempotent term snapshot and anonymized enrollment decisions in the active policy-term namespace. Mem0 uses a content fingerprint for deduplication; the batch ID is not stored in Mem0. |
| `get_late_life_event_attempts()` | Reads policy-term history and returns life-event additions explicitly flagged as outside the configured intimation window. |
| `get_employee_policy_context()` | Reads one employee's enrolled dependent tree, mid-term life-event records, and prior claims for the active policy term. |
| `record_memory()` | Stores a sanitized policy-term summary in the same stable corporate-plus-policy-start namespace, allowing context to accumulate across monthly batches. |
| `save_docket()` | Writes the final JSON file to the selected output directory. |
| `rehydrate_for_display()` | Replaces tokens in a temporary display copy; the persisted JSON remains anonymized. |

## Decision Rules

1. Invalid CSV rows are reported and excluded from processing.
2. Records outside the selected corporate account are ignored; no matching valid record causes the batch to fail.
3. A family or life-event exception rejects that employee's endorsement line. A life-event intimation later than `PolicyTerms.life_event_window_days` (normally 30 days) is stored with `outside_life_event_window: true`.
4. Only approved lines are sent to the actuarial MCP service.
5. A missing MCP calculation produces `TBD` values and fails the docket guardrails.
6. A negative CD closing balance is blocked.
7. The JSON output keeps corporate and employee identifiers anonymized. Rehydration is only for the local CLI-style display.

## Long-Term Policy-Term Memory

Context is maintained for the active policy term rather than for a single batch:

- `LocalHistoryStore._state_user_id()` creates a stable namespace from the corporate account and policy start date.
- `get_latest_batch()` restores the latest closing CD balance before the next batch is processed.
- `get_enrollment_history()` retains anonymized enrollment decisions across monthly batches.
- `get_late_life_event_attempts()` returns life-event additions marked outside the configured window.
- `record_memory()` adds a sanitized term summary to the same namespace.

The batch ID remains available to orchestration and tracing, but it is not
stored in Mem0 memories or enrollment context.

Employee-level context includes the enrolled dependent tree, mid-term life-event
dates such as marriage or child birth, and prior claim records such as settled
status and amount when supplied by the census source. `get_employee_policy_context()`
retrieves these records across monthly batches by filtering the stable
corporate-plus-policy-term history for the anonymized employee token. This
avoids duplicating each record in a second Mem0 namespace.

## Policy Search Flow

The separate policy-information workflow follows:

```text
Question + corporate account
        -> ensure_policy_index()
        -> search_qdrant(..., policy_only=True)
        -> generate_rag_answer()
        -> answer + retrieved SLA evidence + timings
```

The batch demo currently uses its FAISS retrieval path through
`MilestoneDemoService.retrieve_policy()`, while the standalone policy query
service uses Qdrant through `services/rag_service.py`.