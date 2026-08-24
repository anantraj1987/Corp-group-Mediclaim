#Detects adversarial prompt injections and jailbreak attempts designed to hijack agent instructions.
import re
from utils.logger import logger


class PromptInjectionDetector:
    """Detects adversarial jailbreaks, system prompt overrides, and injection attacks."""

    def __init__(self):
        self.injection_keywords = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"disregard\s+(all\s+)?prior\s+prompts",
            r"you\s+are\s+now\s+a\s+DAN",
            r"system\s*:\s*override",
            r"print\s+(your\s+)?system\s+prompt",
            r"show\s+me\s+your\s+initial\0\ instructions",
            r"forget\s+everything\s+you\s+were\s+told",
            r"act\s+as\s+an\s+unfiltered\s+AI",
        ]

    def is_injection_attack(self, text: str) -> bool:
        """Scans input text for adversarial injection triggers."""
        if not text:
            return False

        for pattern in self.injection_keywords:
            if re.search(pattern, text, re.IGNORECASE):
                logger.error(f"[GUARDRAIL SECURITY] Prompt Injection detected! Pattern match: '{pattern}'")
                return True

        return False


injection_detector = PromptInjectionDetector()
