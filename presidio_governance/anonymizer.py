# presidio_governance/anonymizer.py

import hashlib
from typing import Tuple, Dict
from presidio_governance.analyzer import presidio_analyzer_service
from utils.logger import logger


class PresidioReversibleAnonymizer:
    """Anonymizes text with deterministic tokens and supports reverse re-hydration."""

    def anonymize_and_map(
        self, text: str, job_token_map: Dict[str, str] | None = None
    ) -> Tuple[str, Dict[str, str]]:
        """
        Detects PII via Presidio Analyzer and replaces matches with reversible session tokens.
        
        Returns:
            Tuple[anonymized_text, token_to_real_value_map]
        """
        if not text:
            return text, {}

        # 1. Run Presidio Analyzer
        analysis_results = presidio_analyzer_service.analyze_text(text)
        if not analysis_results:
            return text, {}

        token_map = job_token_map if job_token_map is not None else {}
        replacements: list[tuple[int, int, str]] = []

        # Replace spans from right to left so offsets remain valid.
        for result in sorted(analysis_results, key=lambda item: (item.start, -item.end)):
            entity_type = result.entity_type
            real_val = text[result.start:result.end]
            existing_token = next(
                (token for token, value in token_map.items() if value == real_val), None
            )
            if existing_token:
                token = existing_token
            else:
                digest = hashlib.sha256(f"{entity_type}:{real_val}".encode()).hexdigest()[:8]
                token = f"<ANON_{entity_type}_{digest}>"
                token_map[token] = real_val
            replacements.append((result.start, result.end, token))

        anonymized_text = text
        for start, end, token in sorted(replacements, reverse=True):
            anonymized_text = anonymized_text[:start] + token + anonymized_text[end:]

        logger.info(f"[PRESIDIO] Anonymized {len(analysis_results)} PII entities into reversible tokens.")
        return anonymized_text, token_map


# Instantiate global anonymizer service
presidio_anonymizer_service = PresidioReversibleAnonymizer()
