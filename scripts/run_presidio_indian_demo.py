"""Standalone demo: anonymize Indian GMC identifiers, then re-hydrate them back.

Run directly:
    .venv\\Scripts\\python.exe scripts\\run_presidio_indian_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from presidio_governance.anonymizer import presidio_anonymizer_service
from presidio_governance.rehydrator import presidio_rehydrator_service

SAMPLE_TEXT = (
    "Employee EMP-102938 (DOB 15-06-1990, Aadhaar 1234 5678 9012) works at "
    "TechCorp India Pvt Ltd, contact hr.desk@techcorp.in. "
    "Repeat reference to EMP-102938 for the same case."
)


def main() -> None:
    print("=== ORIGINAL TEXT ===")
    print(SAMPLE_TEXT)

    anonymized_text, token_map = presidio_anonymizer_service.anonymize_and_map(SAMPLE_TEXT)
    print("\n=== ANONYMIZED TEXT (sent to LLM / vector store / traces) ===")
    print(anonymized_text)

    print("\n=== TOKEN MAP (kept local only, never leaves this process) ===")
    for token, real_value in token_map.items():
        print(f"  {token} -> {real_value}")

    rehydrated_text = presidio_rehydrator_service.rehydrate_text(anonymized_text, token_map)
    print("\n=== REHYDRATED TEXT (authorized final rendering) ===")
    print(rehydrated_text)

    assert rehydrated_text == SAMPLE_TEXT, "Rehydration did not fully restore the original text."
    print("\nRound-trip check passed: rehydrated text matches the original.")


if __name__ == "__main__":
    main()
