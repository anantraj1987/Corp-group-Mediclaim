from presidio_governance.analyzer import presidio_analyzer_service
from presidio_governance.anonymizer import presidio_anonymizer_service


def _entity_types(text: str) -> set[str]:
    return {result.entity_type for result in presidio_analyzer_service.analyze_text(text)}


def test_employee_id_recognizer():
    types = _entity_types("Employee EMP-102938 raised a query about coverage.")
    assert "ENTERPRISE_EMP_ID" in types


def test_aadhaar_number_recognizer():
    types = _entity_types("Dependent Aadhaar number is 1234 5678 9012 for verification.")
    assert "AADHAAR_NUMBER" in types


def test_corporate_account_recognizer():
    types = _entity_types("The policy is issued to TechCorp India Pvt Ltd for FY2026.")
    assert "CORPORATE_ACCOUNT" in types


def test_indian_dob_recognizer():
    types = _entity_types("Employee date of birth recorded as 15-06-1990 on file.")
    assert "INDIAN_DOB" in types


def test_combined_batch_anonymizes_all_indian_identifiers():
    text = (
        "Employee EMP-102938 (DOB 15-06-1990, Aadhaar 1234 5678 9012) works at "
        "TechCorp India Pvt Ltd, contact hr.desk@techcorp.in."
    )
    anonymized, token_map = presidio_anonymizer_service.anonymize_and_map(text)

    assert "EMP-102938" not in anonymized
    assert "1234 5678 9012" not in anonymized
    assert "15-06-1990" not in anonymized
    assert "TechCorp India Pvt Ltd" not in anonymized
    assert "hr.desk@techcorp.in" not in anonymized
    assert len(token_map) >= 5
