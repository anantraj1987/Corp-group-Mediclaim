from typing import Type, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel
from config.settings import settings
from utils.logger import logger


class OpenAIService:
    """Wrapper service providing configured LLM instances and structured execution chains."""

    def __init__(self):
        settings.validate()
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL_NAME if settings.OPENAI_MODEL_NAME != "gpt-5-mini" else "gpt-4o-mini",
            temperature=settings.TEMPERATURE,
            api_key=settings.OPENAI_API_KEY,
        )

    def execute_prompt(
        self,
        system_prompt: str,
        user_input: str,
        output_schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        """Executes a structured or unstructured prompt against the LLM."""
        try:
            prompt = ChatPromptTemplate.from_messages(
                [("system", system_prompt), ("user", "{input}")]
            )

            if output_schema:
                structured_llm = self.llm.with_structured_output(output_schema)
                chain = prompt | structured_llm
            else:
                # Correct LCEL pipeline order: prompt | llm | parser
                chain = prompt | self.llm | StrOutputParser()

            return chain.invoke({"input": user_input})
        except Exception as e:
            logger.error(f"Error executing OpenAI prompt: {str(e)}")
            raise e


openai_service = OpenAIService()
