import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
CENSUS_DIR = DATA_DIR / "census"
POLICY_DIR = DATA_DIR / "policies"
POLICY_TERMS_DIR = DATA_DIR / "policy_terms"

RANDOM_SEED = 2026
TOTAL_CENSUS_RECORDS = 1000

CENSUS_HEADER = [
    "employee_id",
    "company_name",
    "work_email",
    "dob",
    "action_type",
    "members",
    "effective_date",
    "cessation_date",
    "event_date",
    "intimation_date",
    "base_premium",
]

# Bulk monthly HR census for TechCorp India Pvt Ltd, processed 01-Jul-2026.
# Mirrors the sample scenario: policy tenure 01-Jan-2026 to 31-Dec-2026 (365 days),
# Sum Insured INR 5,00,000 (1+3 family floater), CD balance INR 1,20,000 (alert INR 25,000).
# These curated rows are hand-picked edge cases kept for regression coverage; the bulk of
# TOTAL_CENSUS_RECORDS is filled out by generate_synthetic_rows() below, mixed across all
# corporate accounts defined in policy_terms.
CURATED_CENSUS_ROWS = [
    # Approved: new hire addition (self + spouse), effective 15-Jun-2026.
    ["EMP-9041", "TechCorp India Pvt Ltd", "rahul.mehta@techcorp.in", "12-03-1990", "NEW_HIRE_ADDITION",
     "SELF|SPOUSE", "2026-06-15", "", "", "", "6575.34"],
    # Approved: resignation deletion (self + spouse), cessation 30-Jun-2026.
    ["EMP-4412", "TechCorp India Pvt Ltd", "ananya.roy@techcorp.in", "05-11-1988", "RESIGNATION_DELETION",
     "SELF|SPOUSE", "", "2026-06-30", "", "", "6049.31"],
    # Rejected: newborn addition intimated 141 days after event (exceeds 30-day window).
    ["EMP-7120", "TechCorp India Pvt Ltd", "vikram.singh@techcorp.in", "20-01-1985", "LIFE_EVENT_ADDITION",
     "CHILD", "", "", "2026-01-01", "2026-05-22", "850.00"],
    # Rejected: dual parent/parent-in-law cross-selection.
    ["EMP-3108", "TechCorp India Pvt Ltd", "priya.nair@techcorp.in", "09-09-1982", "DEPENDENT_MODIFICATION",
     "PARENT|PARENT_IN_LAW", "2026-07-01", "", "", "", "0.00"],
    # Approved: marriage addition intimated within the 30-day window.
    ["EMP-5533", "TechCorp India Pvt Ltd", "kavita.desai@techcorp.in", "14-02-1993", "LIFE_EVENT_ADDITION",
     "SPOUSE", "", "", "2026-06-10", "2026-06-20", "3200.00"],
    # Rejected: three children breaches the two-child sub-limit.
    ["EMP-6210", "TechCorp India Pvt Ltd", "arjun.kapoor@techcorp.in", "30-07-1980", "DEPENDENT_MODIFICATION",
     "CHILD|CHILD|CHILD", "2026-07-01", "", "", "", "500.00"],
]

FIRST_NAMES = [
    "Rahul", "Ananya", "Vikram", "Priya", "Kavita", "Arjun", "Rohan", "Sneha",
    "Aditya", "Neha", "Karan", "Pooja", "Sanjay", "Divya", "Rajesh", "Meera",
    "Amit", "Shreya", "Vivek", "Anjali", "Suresh", "Nisha", "Manish", "Ritu",
    "Deepak", "Swati", "Gaurav", "Kritika", "Nikhil", "Payal", "Ashish", "Ira",
    "Varun", "Simran", "Aakash", "Tanvi", "Rakesh", "Bhavna", "Siddharth", "Juhi",
    "Harish", "Lakshmi", "Naveen", "Preeti", "Yash", "Charu", "Mohit", "Vidya",
    "Tarun", "Rekha",
]
LAST_NAMES = [
    "Mehta", "Roy", "Singh", "Nair", "Desai", "Kapoor", "Sharma", "Iyer",
    "Gupta", "Verma", "Reddy", "Chatterjee", "Menon", "Bose", "Malhotra", "Joshi",
    "Agarwal", "Pillai", "Chauhan", "Kulkarni", "Bhatia", "Rao", "Trivedi", "Das",
    "Khanna", "Shetty", "Bansal", "Saxena", "Mishra", "Yadav",
]
PARENT_ACTIONS = ["PARENT", "PARENT_IN_LAW"]


def _random_date(rng: random.Random, start: date, end: date) -> date:
    span_days = (end - start).days
    return start + timedelta(days=rng.randint(0, span_days))


def _random_dob(rng: random.Random) -> str:
    dob = _random_date(rng, date(1965, 1, 1), date(2005, 12, 31))
    return dob.strftime("%d-%m-%Y")


def _company_email_domain(company_name: str) -> str:
    slug = _slugify_account_name(company_name)
    tokens = [t for t in slug.split("_") if t not in ("pvt", "ltd", "india", "private", "limited")]
    return "".join(tokens) + ".in"


def generate_synthetic_rows(count: int, companies: list[str], seed: int = RANDOM_SEED) -> list[list[str]]:
    """Generates realistic, business-rule-aware census rows mixed across the given companies."""
    rng = random.Random(seed)
    policy_start = date(2026, 1, 1)
    policy_end = date(2026, 12, 31)
    rows: list[list[str]] = []

    for i in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        company_name = rng.choice(companies)
        employee_id = f"EMP-{10000 + i}"
        work_email = f"{first.lower()}.{last.lower()}{10000 + i}@{_company_email_domain(company_name)}"
        dob = _random_dob(rng)
        action_type = rng.choices(
            ["NEW_HIRE_ADDITION", "RESIGNATION_DELETION", "LIFE_EVENT_ADDITION", "DEPENDENT_MODIFICATION"],
            weights=[30, 25, 25, 20],
        )[0]

        effective_date = cessation_date = event_date = intimation_date = ""
        members = "SELF"
        base_premium = "0.00"

        if action_type == "NEW_HIRE_ADDITION":
            members = rng.choice(["SELF", "SELF|SPOUSE", "SELF|SPOUSE|CHILD", "SELF|CHILD"])
            effective_date = _random_date(rng, policy_start, policy_end).isoformat()
            base_premium = f"{rng.uniform(800, 7500):.2f}"

        elif action_type == "RESIGNATION_DELETION":
            members = rng.choice(["SELF", "SELF|SPOUSE", "SELF|SPOUSE|CHILD", "SELF|CHILD"])
            cessation_date = _random_date(rng, policy_start, policy_end).isoformat()
            base_premium = f"{rng.uniform(800, 7500):.2f}"

        elif action_type == "LIFE_EVENT_ADDITION":
            members = rng.choice(["CHILD", "SPOUSE"])
            event_dt = _random_date(rng, policy_start, policy_end)
            # ~80% of intimations land inside the 30-day SLA window; the rest breach it.
            if rng.random() < 0.8:
                offset_days = rng.randint(0, 30)
            else:
                offset_days = rng.randint(31, 180)
            event_date = event_dt.isoformat()
            intimation_date = (event_dt + timedelta(days=offset_days)).isoformat()
            base_premium = f"{rng.uniform(300, 3500):.2f}"

        else:  # DEPENDENT_MODIFICATION
            effective_date = _random_date(rng, policy_start, policy_end).isoformat()
            roll = rng.random()
            if roll < 0.10:
                members = "PARENT|PARENT_IN_LAW"  # rejected: dual parent cross-selection
            elif roll < 0.20:
                members = "CHILD|CHILD|CHILD"  # rejected: exceeds two-child sub-limit
            elif roll < 0.28:
                members = "SPOUSE|SPOUSE"  # rejected: duplicate member enrollment
            else:
                members = rng.choice(["SPOUSE", "CHILD", "CHILD|CHILD", rng.choice(PARENT_ACTIONS)])
            base_premium = f"{rng.uniform(0, 2000):.2f}"

        rows.append([
            employee_id, company_name, work_email, dob, action_type, members,
            effective_date, cessation_date, event_date, intimation_date, base_premium,
        ])

    return rows

def render_corporate_sla_text(policy_terms: dict) -> str:
    """Renders the GMC master SLA text for a single corporate account's policy terms."""
    account = policy_terms["corporate_account"]
    family_definition = policy_terms["family_definition"]
    max_dependents = 3 if family_definition == "1+3" else 5
    sum_insured = float(policy_terms["sum_insured_inr"])
    cd_balance = float(policy_terms["cd_balance_inr"])
    cd_alert_threshold = float(policy_terms["cd_alert_threshold_inr"])
    life_event_window_days = policy_terms["life_event_window_days"]

    return f"""GMC MASTER SLA - {account}
Policy Tenure: 01-Jan-2026 to 31-Dec-2026 (365 Days)
Sum Insured: INR {sum_insured:,.0f} ({family_definition} Family Floater)

Clause 4.2 - Family Definition
The Corporate Group Mediclaim policy recognizes two family structures:
1+3 (Employee + Spouse + up to 2 Children) or, where explicitly opted, 1+5
(adding either the Employee's Parents OR Parents-in-law, not both concurrently).
Dual enrollment of both biological parents and parents-in-law under the same
employee is strictly prohibited. This account is enrolled under the
{family_definition} structure, permitting a maximum of {max_dependents} dependents
per employee record.

Clause 5.1 - Maternity Sub-Limits
Normal delivery is capped at INR 50,000 and cesarean delivery at INR 75,000
per policy year. A 9-month waiting period applies unless a waiver has been
granted at policy inception for continuity of coverage from the prior insurer.

Clause 5.2 - Day-Care Procedure Approvals
Listed day-care procedures are payable without the standard 24-hour
hospitalization requirement, subject to network provider empanelment.

Clause 6.4 - Life Event Window
Mid-term additions arising from qualifying life events (newborn, marriage,
legal adoption) must be intimated to the TPA within {life_event_window_days} days
of the event date. Intimations received beyond this window are rejected and
require the next policy renewal cycle for enrollment.

Clause 7.1 - Corporate Cash Deposit (CD) Buffer & Replenishment
The corporate CD account funds pro-rata premium debits for additions and
receives pro-rata credits for deletions, inclusive of {policy_terms['gst_rate_percent']}%
GST on the base premium. The current CD balance is INR {cd_balance:,.2f}; a
replenishment alert is raised whenever the closing CD balance falls below the
minimum threshold of INR {cd_alert_threshold:,.2f}.

Clause 8.1 - Enrolled Headcount & Batch Processing
The policy covers the full {account} employee base, with monthly HR census
batches processed per cycle. Each batch row is independently validated against
Clauses 4.2 and 6.4 before inclusion in the endorsement docket; non-conforming
rows are logged as rejected exceptions rather than blocking the remainder of
the batch.
"""

POLICY_TERMS_JSON = {
    "corporate_account": "TechCorp India Pvt Ltd",
    "policy_start_date": "2026-01-01",
    "policy_end_date": "2026-12-31",
    "sum_insured_inr": "500000.00",
    "family_definition": "1+3",
    "gst_rate_percent": "18",
    "life_event_window_days": 30,
    "cd_balance_inr": "120000.00",
    "cd_alert_threshold_inr": "25000.00",
}

# Additional synthetic corporate accounts for multi-tenant eval/test coverage.
OTHER_CORPORATE_ACCOUNTS = [
    "Nimbus Cloudworks Pvt Ltd",
    "Zenith Auto Components Ltd",
    "Bluewave Logistics India Pvt Ltd",
    "Sundale Agro Exports Pvt Ltd",
    "Orbit Fintech Solutions Pvt Ltd",
    "Granite Infra Projects Ltd",
    "Ferrous Steel Works Pvt Ltd",
    "Coral Reef Hospitality Pvt Ltd",
    "Pinnacle Pharma Labs Ltd",
    "Silverline Textiles Pvt Ltd",
    "Meridian Energy Systems Pvt Ltd",
    "Crestview Retail Ventures Pvt Ltd",
    "Northgate Consulting Group Pvt Ltd",
    "Vertex Semiconductors India Pvt Ltd",
    "Harborline Shipping & Freight Pvt Ltd",
]


def generate_synthetic_policy_terms(seed: int = RANDOM_SEED) -> list[dict]:
    """Builds one policy-terms record per entry in OTHER_CORPORATE_ACCOUNTS."""
    rng = random.Random(seed)
    records = []
    for i, account_name in enumerate(OTHER_CORPORATE_ACCOUNTS):
        family_definition = rng.choice(["1+3", "1+5"])
        sum_insured = rng.choice([300000, 400000, 500000, 750000, 1000000])
        cd_balance = round(rng.uniform(50000, 250000), 2)
        cd_alert_threshold = round(cd_balance * rng.uniform(0.1, 0.25), 2)
        records.append({
            "corporate_account": account_name,
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
            "sum_insured_inr": f"{sum_insured:.2f}",
            "family_definition": family_definition,
            "gst_rate_percent": "18",
            "life_event_window_days": rng.choice([15, 30, 45]),
            "cd_balance_inr": f"{cd_balance:.2f}",
            "cd_alert_threshold_inr": f"{cd_alert_threshold:.2f}",
        })
    return records


def generate_census_csv() -> Path:
    CENSUS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CENSUS_DIR / "multi_corporate_july_2026_census.csv"
    all_companies = [POLICY_TERMS_JSON["corporate_account"]] + OTHER_CORPORATE_ACCOUNTS
    synthetic_count = max(TOTAL_CENSUS_RECORDS - len(CURATED_CENSUS_ROWS), 0)
    rows = CURATED_CENSUS_ROWS + generate_synthetic_rows(synthetic_count, all_companies)
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CENSUS_HEADER)
        writer.writerows(rows)
    return file_path


def _slugify_account_name(account_name: str) -> str:
    return (
        account_name.lower()
        .replace(".", "")
        .replace(",", "")
        .replace("&", "and")
        .replace(" ", "_")
    )


def all_policy_terms_records() -> list[dict]:
    return [POLICY_TERMS_JSON] + generate_synthetic_policy_terms()


def generate_corporate_sla_docs() -> list[Path]:
    """Writes one SLA text file per corporate account in policy_terms."""
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    file_paths = []
    for record in all_policy_terms_records():
        file_path = POLICY_DIR / f"{_slugify_account_name(record['corporate_account'])}_gmc_master_sla.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(render_corporate_sla_text(record))
        file_paths.append(file_path)
    return file_paths


def generate_policy_terms() -> Path:
    """Writes a single combined JSON file containing all corporate accounts' policy terms."""
    POLICY_TERMS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = POLICY_TERMS_DIR / "corporate_accounts_2026.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(all_policy_terms_records(), f, indent=2)
    return file_path


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    census_path = generate_census_csv()
    sla_paths = generate_corporate_sla_docs()
    policy_terms_path = generate_policy_terms()
    print(f"Generated bulk employee census ({TOTAL_CENSUS_RECORDS} records): {census_path}")
    print(f"Generated {len(sla_paths)} corporate SLA documents in: {POLICY_DIR}")
    print(f"Generated combined policy terms ({len(OTHER_CORPORATE_ACCOUNTS) + 1} accounts): {policy_terms_path}")


if __name__ == "__main__":
    main()

