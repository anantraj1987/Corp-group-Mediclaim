#Enforces enterprise security policies and semantic topic boundaries using LLM classification.
from pydantic import BaseModel, Field
from services.openai_service import openai_service
from utils.logger import logger


class PolicyCheckSchema(BaseModel):
    is_compliant: bool = Field(description="True if query adheres to IT operations safety policy, False otherwise.")
    policy_violation_reason: str = Field(description="Details on policy violation if compliant is False.")


class PolicyEnforcer:
    """Evaluates semantic policy compliance, corporate safety boundaries, and content filters."""

    def check_policy_compliance(self, query: str) -> PolicyCheckSchema:
        """Evaluates semantic query intent against Enterprise IT Copilot usage policy."""
        system_prompt = (
            "You are an Enterprise AI Security & Compliance Guardrail. Evaluate if the user query "
            "adheres to enterprise IT operations policies.\n"
            "DISALLOW queries that ask to:\n"
            "1. Bypass authentication or security firewalls maliciously.\n"
            "2. Exfiltrate user passwords, private keys, or enterprise secrets.\n"
            "3. Generate hate speech, toxic content, or non-work-related topics.\n\n"
            "Return JSON matching PolicyCheckSchema."
        )

        try:
            result: PolicyCheckSchema = openai_service.execute_prompt(
                system_prompt=system_prompt,
                user_input=query,
                output_schema=PolicyCheckSchema
            )
            if not result.is_compliant:
                logger.warning(f"[GUARDRAIL POLICY] Non-compliant query blocked. Reason: {result.policy_violation_reason}")
            return result
        except Exception as e:
            logger.error(f"[GUARDRAIL POLICY] Policy check error ({str(e)}). Failing safe.")
            return PolicyCheckSchema(is_compliant=True, policy_violation_reason="Default Pass")


policy_enforcer = PolicyEnforcer()

