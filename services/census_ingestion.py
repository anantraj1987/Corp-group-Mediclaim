import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from schemas.gmc_schemas import CensusIngestionResult, CensusMember


HEADER_ALIASES = {
    "company_name": "corporate_account",
    "corporate_account": "corporate_account",
    "employee_id": "employee_identifier",
    "employee_identifier": "employee_identifier",
    "emp_id": "employee_identifier",
    "corporate_email": "corporate_email",
    "work_email": "corporate_email",
    "email": "corporate_email",
    "aadhaar": "aadhaar",
    "aadhaar_number": "aadhaar",
    "company_name": "corporate_account",
    "corporate_account": "corporate_account",
    "dob": "date_of_birth",
    "date_of_birth": "date_of_birth",
    "action": "action_type",
    "action_type": "action_type",
    "members": "members",
    "members_covered": "members",
    "members_removed": "members",
    "coverage_effective_date": "coverage_effective_date",
    "effective_date": "coverage_effective_date",
    "coverage_cessation_date": "coverage_cessation_date",
    "cessation_date": "coverage_cessation_date",
    "event_date": "event_date",
    "intimation_date": "intimation_date",
    "base_premium_inr": "base_premium_inr",
    "base_premium": "base_premium_inr",
}


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return HEADER_ALIASES.get(normalized, normalized)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {value}")


def _parse_members(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return [item.strip().upper() for item in str(value).replace("|", ",").split(",") if item.strip()]


def _parse_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    cleaned = str(value).replace(",", "").replace("₹", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(f"invalid premium amount: {value}") from error


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    normalized["date_of_birth"] = _parse_date(normalized.get("date_of_birth"))
    for field in ("coverage_effective_date", "coverage_cessation_date", "event_date", "intimation_date"):
        normalized[field] = _parse_date(normalized.get(field))
    normalized["members"] = _parse_members(normalized.get("members"))
    normalized["base_premium_inr"] = _parse_decimal(normalized.get("base_premium_inr"))
    return normalized


def _parse_rows(rows: Iterable[dict[str, Any]], source_format: str) -> CensusIngestionResult:
    records: list[CensusMember] = []
    row_errors: list[dict[str, Any]] = []
    seen_identifiers: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        try:
            normalized = _normalize_row(row)
            identifier = str(normalized.get("employee_identifier", "")).strip()
            if not identifier:
                raise ValueError("employee_identifier is required")
            if identifier in seen_identifiers:
                raise ValueError("duplicate employee_identifier in census batch")
            seen_identifiers.add(identifier)
            records.append(CensusMember(**normalized))
        except (ValueError, ValidationError) as error:
            row_errors.append({"row": row_number, "error": str(error)})

    return CensusIngestionResult(records=records, row_errors=row_errors, source_format=source_format)


def ingest_csv(source: str | bytes | Path) -> CensusIngestionResult:
    if isinstance(source, Path):
        content = source.read_text(encoding="utf-8-sig")
    elif isinstance(source, bytes):
        content = source.decode("utf-8-sig")
    else:
        content = source
    return _parse_rows(csv.DictReader(io.StringIO(content)), "csv")


def ingest_xlsx(source: str | bytes | Path) -> CensusIngestionResult:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("XLSX ingestion requires pandas and openpyxl") from error

    if isinstance(source, (str, Path)):
        frame = pd.read_excel(source, engine="openpyxl")
    else:
        frame = pd.read_excel(io.BytesIO(source), engine="openpyxl")
    rows = frame.where(frame.notna(), None).to_dict(orient="records")
    return _parse_rows(rows, "xlsx")