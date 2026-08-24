from datetime import date
from typing import Iterable

from schemas.gmc_schemas import PolicyTerms, RejectedException


_PARENT_TYPES = {"PARENT", "PARENT_IN_LAW"}


def validate_family_members(
    employee_identifier_anonymized: str,
    members: Iterable[str],
    policy: PolicyTerms,
    action_type="DEPENDENT_MODIFICATION",
    sla_reference: str | None = None,
) -> list[RejectedException]:
    normalized = [member.strip().upper() for member in members]
    exceptions: list[RejectedException] = []
    counts = {member: normalized.count(member) for member in set(normalized)}

    duplicate_members = sorted(member for member, count in counts.items() if count > 1)
    if duplicate_members:
        exceptions.append(
            RejectedException(
                employee_identifier_anonymized=employee_identifier_anonymized,
                attempted_action=action_type,
                rejection_reason=f"Duplicate family member enrollment: {', '.join(duplicate_members)}.",
                sla_reference=sla_reference,
            )
        )

    parent_types = _PARENT_TYPES.intersection(normalized)
    if len(parent_types) > 1:
        exceptions.append(
            RejectedException(
                employee_identifier_anonymized=employee_identifier_anonymized,
                attempted_action=action_type,
                rejection_reason="Cross-selection breach: policy allows either biological parents or parents-in-law, not both sets concurrently.",
                sla_reference=sla_reference,
            )
        )

    child_count = counts.get("CHILD", 0)
    dependent_count = len([member for member in normalized if member != "SELF"])
    maximum_dependents = 3 if policy.family_definition == "1+3" else 5
    if dependent_count > maximum_dependents:
        exceptions.append(
            RejectedException(
                employee_identifier_anonymized=employee_identifier_anonymized,
                attempted_action=action_type,
                rejection_reason=f"Family definition breach: {policy.family_definition} permits at most {maximum_dependents} dependents.",
                sla_reference=sla_reference,
            )
        )
    if child_count > 2:
        exceptions.append(
            RejectedException(
                employee_identifier_anonymized=employee_identifier_anonymized,
                attempted_action=action_type,
                rejection_reason="Child limit breach: policy permits a maximum of two children.",
                sla_reference=sla_reference,
            )
        )
    return exceptions


def validate_life_event_window(
    employee_identifier_anonymized: str,
    action_type,
    event_date: date,
    intimation_date: date,
    policy: PolicyTerms,
    sla_reference: str | None = None,
) -> RejectedException | None:
    gap_days = (intimation_date - event_date).days
    if gap_days < 0:
        return RejectedException(
            employee_identifier_anonymized=employee_identifier_anonymized,
            attempted_action=action_type,
            rejection_reason="Intimation date cannot precede the life-event date.",
            sla_reference=sla_reference,
        )
    if gap_days > policy.life_event_window_days:
        return RejectedException(
            employee_identifier_anonymized=employee_identifier_anonymized,
            attempted_action=action_type,
            rejection_reason=(
                f"Intimation gap of {gap_days} days exceeds the mandatory "
                f"{policy.life_event_window_days}-day mid-term life-event window."
            ),
            sla_reference=sla_reference,
        )
    return None
