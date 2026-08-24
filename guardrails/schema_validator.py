#Performs strict Regex and structural schema validation on queries and system outputs.
import re
from typing import Tuple, List
from utils.logger import logger


class SchemaValidator:
    """Regex and structural validation engine for input and output state payloads."""

    def __init__(self):
        # Disallow raw SQL destructive statements or unauthorized system shell commands in queries
        self.forbidden_patterns = [
            r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)\b",
            r"\b(rm\s+-rf\s+/|mkfs\b|dd\s+if=)\b",
            r"\b(sudo\s+chmod\s+-R\s+777\s+/)\b",
        ]

    def validate_input_query(self, query: str) -> Tuple[bool, str]:
        """Validates raw input query against length, syntax, and forbidden destructive patterns."""
        if not query or not query.strip():
            return False, "Input query cannot be empty."

        if len(query) > 2000:
            return False, "Input query exceeds maximum allowed length of 2000 characters."

        for pattern in self.forbidden_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                logger.warning(f"[GUARDRAIL] Destructive command pattern detected in input: {pattern}")
                return False, f"Query contains unauthorized destructive system command pattern."

        return True, "Valid"


schema_validator = SchemaValidator()

