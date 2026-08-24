import re
from types import SimpleNamespace

try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
except ImportError:
    AnalyzerEngine = None
    PatternRecognizer = None
    Pattern = None
from utils.logger import logger


class EnterprisePresidioAnalyzer:
    """Presidio ML-driven PII Analyzer with custom domain recognizers."""

    def __init__(self):
        self.analyzer = AnalyzerEngine() if AnalyzerEngine is not None else None
        self.fallback_patterns = [
            ("ENTERPRISE_EMP_ID", re.compile(r"\bEMP[-_]\d{4,10}\b")),
            ("AADHAAR_NUMBER", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")),
            ("INDIAN_DOB", re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[-/]\d{1,2}[-/]\d{4}\b")),
            ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
        ]

        if self.analyzer is None:
            logger.warning("[PRESIDIO] Native Presidio unavailable; using local regex fallback.")
            return

        recognizers = [
            PatternRecognizer(
                supported_entity="ENTERPRISE_EMP_ID",
                patterns=[Pattern(name="emp_id_pattern", regex=r"\bEMP[-_]\d{4,10}\b", score=0.95)],
                context=["employee", "staff", "badge", "worker"],
            ),
            PatternRecognizer(
                supported_entity="AADHAAR_NUMBER",
                patterns=[Pattern(name="aadhaar_pattern", regex=r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b", score=0.9)],
                context=["aadhaar", "uid", "dependent"],
            ),
            PatternRecognizer(
                supported_entity="CORPORATE_ACCOUNT",
                patterns=[Pattern(name="corp_account_pattern", regex=r"\b[A-Z][A-Z0-9]{2,20}\s+(?:India|Pvt|Private|Ltd|Limited)\b", score=0.75)],
                context=["corporate", "client", "account", "policy"],
            ),
            PatternRecognizer(
                supported_entity="INDIAN_DOB",
                patterns=[Pattern(name="indian_dob_pattern", regex=r"\b(?:0?[1-9]|[12]\d|3[01])[-/]\d{1,2}[-/]\d{4}\b", score=0.9)],
                context=["dob", "birth", "born", "date"],
            ),
        ]
        for recognizer in recognizers:
            self.analyzer.registry.add_recognizer(recognizer)
        logger.info("[PRESIDIO] Initialized analyzer with GMC employee, Aadhaar, corporate, and DOB recognizers.")

    def analyze_text(self, text: str, score_threshold: float = 0.6) -> list:
        """Scans text for PII entities using NER and custom regex pattern recognizers."""
        if not text:
            return []

        if self.analyzer is None:
            results = []
            for entity_type, pattern in self.fallback_patterns:
                results.extend(
                    SimpleNamespace(
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        score=0.9,
                    )
                    for match in pattern.finditer(text)
                )
            return sorted(results, key=lambda item: (item.start, -item.end))

        results = self.analyzer.analyze(
            text=text,
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                "IP_ADDRESS", "CREDIT_CARD", "ENTERPRISE_EMP_ID",
                "AADHAAR_NUMBER", "CORPORATE_ACCOUNT", "INDIAN_DOB"
            ],
            language="en",
            score_threshold=score_threshold
        )
        return results


presidio_analyzer_service = EnterprisePresidioAnalyzer()