#Redacts sensitive PII data (credit cards, Social Security Numbers, AWS Secret Keys, passwords, Bearer tokens, IP addresses, and email addresses) before inputs enter the graph or output to users.
import re
from utils.logger import logger


class PIISanitizer:
    """Detects and redacts sensitive PII and credential tokens using Regex rules."""

    def __init__(self):
        self.pii_patterns = {
            "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "IP_ADDRESS": r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
            "AWS_SECRET_KEY": r"(?i)(aws_secret_access_key|aws_key|secret_key)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
            "BEARER_TOKEN": r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*",
            "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
            "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
            "PASSWORD_ASSIGNMENT": r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?",
        }

    def sanitize_text(self, text: str) -> str:
        """Scans text and replaces PII tokens with sanitized placeholders."""
        if not text:
            return text

        sanitized_text = text
        redaction_counts = {}

        for pii_type, pattern in self.pii_patterns.items():
            matches = re.findall(pattern, sanitized_text)
            if matches:
                redaction_counts[pii_type] = len(matches)
                sanitized_text = re.sub(pattern, f"[REDACTED_{pii_type}]", sanitized_text)

        if redaction_counts:
            logger.warning(f"[GUARDRAIL PII] Redacted sensitive elements: {redaction_counts}")

        return sanitized_text


pii_sanitizer = PIISanitizer()
