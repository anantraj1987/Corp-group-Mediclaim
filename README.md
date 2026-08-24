 # Corporate Group Mediclaim Copilot

The GMC implementation is being migrated locally from the previous incident-agent scaffold.

The first implemented slice contains:

- Pydantic contracts for policy terms, census members, endorsement lines, exceptions, CD health, and endorsement dockets.
- Decimal-based pro-rata premium, GST, deletion-credit, and CD balance calculations.
- Deterministic family-definition and life-event-window validation.
- CSV census ingestion with normalized headers, typed dates/premiums, duplicate detection, and row-level errors.
- Presidio GMC recognizers for employee IDs, Aadhaar numbers, corporate email, and Indian DOB formats.

All data is synthetic and local. No Git integration or external insurer/TPA connection is used.
