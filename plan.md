# Corporate GMC & GPA Endorsement Copilot Plan

## 1. Objective

Build an auditable assistant for Indian corporate Group Mediclaim (GMC) and Group Personal Accident (GPA) operations. The system will ingest monthly HR census changes and corporate policy documents, protect employee and dependent PII, calculate endorsement financial impact, enforce policy rules, and produce insurer-ready JSON dockets with traceable SLA citations.

The system must follow two evidence boundaries:

- Policy eligibility, limits, waivers, waiting periods, and deadlines must be supported only by the retrieved corporate contract.
- Employee and dependent identifiers must be anonymized before data is sent to an LLM or vector store. Re-identification is allowed only in the local docket assembly step.

All development data in this repository is synthetic and local.

## 2. Current Repository Baseline

### Already available

- Synthetic census data under `data/census/`, including monthly additions, deletions, and life-event records.
- CSV/XLSX normalization and row-level validation in `services/census_ingestion.py`.
- GMC Pydantic contracts in `schemas/gmc_schemas.py` for policy terms, census members, endorsement lines, dockets, exceptions, and CD health.
- Decimal-based pro-rata premium, GST, deletion credit, and CD calculations in `services/endorsement_calculator.py`.
- Family definition and life-event validation modules in `services/family_rules.py`.
- Presidio recognizers and anonymization components under `presidio_governance/` and `guardrails/`.
- Corporate policy documents under `data/policies/` and existing FAISS artifacts under `data/faiss_index/`.
- In-progress clause-aware chunking and local Qdrant retrieval in `services/chunking.py` and `services/qdrant_service.py`.
- In-progress policy-only RAG answer generation and citation instructions in `services/rag_service.py`.
- LangGraph orchestration, guardrail nodes, MCP service modules, and a Streamlit entry point.

### Gaps to close

- Make policy ingestion reproducible, idempotent, and scoped to the requested corporate contract.
- Preserve clause headings and exact source locations through chunking, indexing, retrieval, and answer generation.
- Add citation validation so an LLM cannot invent a clause reference or answer from general knowledge.
- Define a single canonical vector-store path and document whether Qdrant or FAISS is the production backend.
- Ensure no raw census PII reaches embeddings, Qdrant, prompts, logs, caches, or traces.
- Connect policy retrieval and endorsement validation to the LangGraph flow.
- Add persistent policy-term and employee-history memory, MCP calculation tools, deterministic docket assembly, and end-to-end tests.
- Complete dependency/configuration validation for the selected RAG backend and model settings.

## 3. Target Architecture

```text
HR census CSV/XLSX                         Corporate policy/SLA files
				|                                           |
				v                                           v
 Census ingestion -> Presidio scan/anonymize   Policy loader -> clause chunker
				|                                           |
				v                                           v
 Local token map + validated records          Embeddings -> vector store
				|                                           |
				+--------------------+----------------------+
														 v
										LangGraph endorsement flow
														 |
			 +---------------------+----------------------+
			 v                     v                      v
	Mem0 policy/history   Deterministic rules     MCP calculations
			 |                     |                      |
			 +---------------------+----------------------+
														 v
							Pydantic docket + citation validator
														 |
														 v
								 Local rehydration and audit output
```

## 4. Milestone Roadmap

### Milestone 1: Privacy and Census Ingestion

#### Deliverables

- Support CSV and Excel uploads with normalized headers and typed dates, members, and premiums.
- Validate required identifiers, action types, duplicate rows, date formats, and invalid premium values.
- Add and test Presidio recognizers for:
	- Corporate employee IDs
	- Aadhaar numbers
	- Corporate/work email addresses
	- Indian DOB formats
- Anonymize employee, dependent, and corporate identifiers before LLM/vector-store boundaries.
- Store the reversible token map locally with restricted access and an explicit request/batch scope.
- Preserve a sanitized, insurer-ready internal representation without exposing raw PII in logs.

#### Acceptance criteria

- Valid monthly census files produce typed `CensusMember` records.
- Invalid rows are rejected individually without hiding valid rows.
- Duplicate employee identifiers are detected within a batch.
- Recognizer tests cover positive, negative, and false-positive cases.
- A test proves raw PII is absent from sanitized prompts, embeddings, vector payloads, and audit logs.

#### Main code areas

`services/census_ingestion.py`, `presidio_governance/`, `guardrails/pii_sanitizer.py`, `schemas/gmc_schemas.py`, `tests/test_presidio_indian_recognizers.py`.

### Milestone 2: Corporate SLA and Policy Master RAG

#### Deliverables

- Load corporate GMC master wordings, waiver clauses, sub-limit rules, endorsement schedules, and HR benefit rulebooks from `data/policies/`.
- Parse documents by clause/section and retain:
	- Corporate contract name
	- Policy document filename and version
	- Clause number and exact clause title
	- Source character/page location when available
	- Effective policy period
- Chunk without separating a clause heading from its rule text. Add controlled overlap only when needed.
- Index sanitized policy text with deterministic point IDs and idempotent upserts.
- Choose and document one default backend. Keep FAISS only as a migration or offline evaluation path if Qdrant is selected.
- Retrieve only policy/SLA documents for eligibility questions, with corporate-account filtering where possible.
- Generate answers strictly from retrieved chunks and return exact citations in the format:

	`[Source: <filename> | Clause: <Clause X.Y>]`

- Add a citation validator that rejects citations not present in the retrieved evidence and returns an explicit `INSUFFICIENT_CONTRACT_EVIDENCE` result when the contract is silent.

#### Acceptance criteria

- A query about maternity, waiting-period waivers, day-care, family definition, or buffer/sub-limit usage returns the relevant contract clause.
- Cross-corporate retrieval cannot use another company’s contract.
- Every eligibility or numeric policy claim has a valid source filename and clause reference.
- No-context and low-confidence queries do not receive inferred or generic coverage answers.
- An index rebuild produces stable counts, metadata, and retrieval results for the same inputs.
- Retrieval and answer generation expose latency and source metadata for audit/debugging.

#### Main code areas

`services/chunking.py`, `services/qdrant_service.py`, `services/rag_service.py`, `data/policies/`, `data/policy_terms/`, `config/settings.py`, and new RAG tests.

### Milestone 3: Memory and Actuarial Tools

#### Deliverables

- Persist policy-term context and corporate CD balances in Mem0 or the selected durable store.
- Track sanitized employee/family enrollment history and monthly census changes by policy term.
- Detect additions outside the standard 30-day life-event intimation window.
- Expose MCP/tool endpoints for:
	- Pro-rata premium
	- GST
	- Deletion credit
	- CD debit/credit and solvency checks
- Keep all monetary calculations in `Decimal`; define rounding and day-count rules centrally.

#### Acceptance criteria

- Repeated monthly batches are idempotent and do not double-charge or double-credit a member.
- Life-event decisions use event date, intimation date, policy terms, and the retrieved SLA reference.
- CD closing balance and alert status reconcile exactly with calculated line items.
- An overdraft is blocked deterministically before docket approval.

#### Main code areas

`services/memory_service.py`, `services/endorsement_calculator.py`, `services/family_rules.py`, `mcp_services/`, `schemas/gmc_schemas.py`, and calculation/history tests.

#### Implemented Local Demo Slice

- Mem0 persists sanitized corporate batch summaries using the local Qdrant store at `data/.mem0_qdrant`.
- `LocalHistoryStore` persists idempotent batch records and anonymized enrollment history in `data/memory_history.json`.
- `services/actuarial_tools.py` exposes Decimal-based pro-rata premium, deletion credit, GST, and CD health functions.
- `mcp_services/gmc_actuarial_service.py` exposes the actuarial functions through MCP-compatible `/mcp/tools` and `/mcp/invoke` endpoints.
- CD overdrafts raise `CashDepositOverdraftError` before a docket can be approved.
- Deletion credits count unexpired coverage from the day after cessation; all money values use two-decimal `Decimal` rounding.
- The TechCorp CLI fixture verifies idempotent history, life-event/family exceptions, exact CD reconciliation, and guardrail status.

### Milestone 4: Autonomous Endorsement Agent and Guardrails

#### Deliverables

- Add a dedicated GMC endorsement path to the LangGraph state and routing model.
- Implement the flow:
	1. Validate and classify the census batch.
	2. Sanitize identifiers and create the local token map.
	3. Load the applicable corporate policy terms.
	4. Retrieve and cite the controlling SLA clauses.
	5. Validate family definitions, parent cross-selection, life events, and policy dates.
	6. Invoke deterministic calculation tools.
	7. Assemble the docket.
	8. Validate output and require human approval for unresolved exceptions or low confidence.
- Validate the final output against `EndorsementDocket`.
- Enforce mathematical parity between line items and account health.
- Block missing evidence, invalid citations, overdrafts, and unsafe rehydration.

#### Acceptance criteria

- The sample TechCorp scenario produces the target docket structure and expected premium/CD values.
- Rejected exceptions include a deterministic reason and SLA reference when a rule is contract-backed.
- The final JSON contains only anonymized identifiers until the local insurer-output step.
- Failed guardrails cannot be emitted as an approved docket.

#### Main code areas

`graph/`, `nodes/`, `guardrails/`, `services/docket_assembler.py`, `schemas/gmc_schemas.py`, and end-to-end graph tests.

### Milestone 5: Observability and HR Dashboard

#### Deliverables

- Add LangSmith traces for ingestion, sanitization, retrieval, citations, tool calls, guardrails, and final docket status.
- Redact PII from traces, error messages, and metrics.
- Build Streamlit/Chainlit workflows for census upload, policy selection, validation summary, exceptions, citations, CD health, and docket download.
- Add batch IDs, policy-term IDs, index version, model version, and timestamps to audit records.
- Provide operational metrics for retrieval quality, citation validity, processing latency, rejected rows, exceptions, and CD alerts.

#### Acceptance criteria

- HR users can upload a census file and review approved/rejected lines before finalization.
- Every displayed rejection and policy decision links to its source clause or explicitly says evidence is unavailable.
- A complete run can be reconstructed from its batch ID without exposing raw PII.
- Desktop and mobile-width layouts remain usable for the review workflow.

#### Main code areas

`streamlit_app.py`, `app.py`, `utils/logger.py`, `services/`, `evals/`, and observability configuration.

## 5. Immediate Implementation Sequence

1. Resolve configuration and dependency consistency for the selected vector backend and chat model.
2. Add a policy indexer command/service that reads `data/policies/`, chunks clauses, embeds them, and records index metadata.
3. Harden chunk metadata and add exact clause/source-location fields.
4. Add corporate-account and policy-version filters to retrieval.
5. Add citation parsing/validation and an insufficient-evidence response path.
6. Create focused RAG tests using a fake embedding/search layer; keep network calls out of unit tests.
7. Connect `answer_policy_query` to the GMC graph path.
8. Integrate policy retrieval into family/life-event validation and docket assembly.
9. Add end-to-end tests for the sample scenario and cross-corporate isolation.

### First CLI Demonstration

The first executable slice is available through `app.py` and uses the local FAISS
policy index:

```powershell
python app.py --rebuild --query "What is the maternity limit and waiting period?" `
	--corporate "Nimbus Cloudworks" --retrieve-only --top-k 3
```

Use `--retrieve-only` to inspect contract evidence without an LLM call. Remove it
to generate a contract-grounded answer with citations. The `--corporate` filter is
important for preventing a query from mixing clauses from different corporate
contracts. Rebuilding is required after policy files or chunk metadata change.

## 6. Testing and Evaluation Strategy

### Unit tests

- Census header normalization, date/member/premium parsing, duplicates, and row errors.
- PII recognizer precision and anonymization/re-hydration boundaries.
- Clause parsing, chunk overlap, deterministic IDs, and metadata preservation.
- Retrieval filters, citation validation, and insufficient evidence.
- Family rules, life-event windows, pro-rata/GST/CD arithmetic, and schema validation.

### Integration tests

- Policy files -> chunks -> vector store -> retrieved evidence.
- Sanitized census -> endorsement lines -> calculations -> docket.
- LangGraph route through guardrails, retrieval, tools, human approval, and output validation.

### Evaluation set

Create a versioned set of questions and expected clauses for maternity limits, waiting-period waivers, day-care approvals, family definitions, parent cross-selection, buffer/sub-limits, and life-event windows. Measure retrieval recall, citation validity, unsupported-claim rate, answer completeness, latency, and token cost.

## 7. Security and Data Rules

- Never send raw employee IDs, Aadhaar numbers, DOBs, emails, salary information, or token maps to OpenAI, Mem0, Qdrant/FAISS, LangSmith, Redis, or application logs.
- Use least-privilege access for token maps and local policy/census files.
- Treat policy documents as versioned evidence; do not silently overwrite an active policy term.
- Separate corporate contracts at ingestion and retrieval time.
- Validate all uploaded files, enforce size/type limits, and reject malformed or unexpected columns.
- Make audit records append-only where operationally possible.
- Keep secrets in environment configuration and never commit `.env` or API keys.

## 8. Definition of Done

The project is complete when an HR user can upload a synthetic monthly census, select the applicable corporate policy term, review sanitized and calculated endorsement lines, see contract-backed citations for every policy decision, resolve or approve exceptions, and export a Pydantic-validated docket. The run must be reproducible and auditable by batch ID, must preserve CD arithmetic exactly, and must not expose employee PII outside the local rehydration boundary.
