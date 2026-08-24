import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path if env_path.exists() else None)


class Settings:
    PROJECT_NAME: str = "Corporate Group Mediclaim"
    VERSION: str = "2.0.0"

    # OpenAI API Configurations
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))

    #qdrant Configuration
    QDRANT_COLLECTION_NAME: str = "enterprise_mediclaim_collection"
    QDRANT_DIR: Path= BASE_DIR / "qdrant_db"

    # System Operational Limits
    MAX_RETRY_COUNT: int = 2
    CONFIDENCE_THRESHOLD: int = 70

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "98.84.124.251")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_CACHE_TTL: int = int(os.getenv("REDIS_CACHE_TTL", "3600"))  # Cache TTL in seconds

    # Mem0 Configuration
    MEM0_API_KEY: str = os.getenv("MEM0_API_KEY", "")

    # Remote MCP Microservice URLs & Ports
    MCP_GMC_ACTUARIAL_URL: str = os.getenv(
      "MCP_GMC_ACTUARIAL_URL", "http://localhost:8001"
    )

  # API Security & Authentication Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "super-secret-enterprise-jwt-key-change-in-prod")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 Hours

    # Paths
    DATA_DIR: Path = BASE_DIR / "data"
    KB_FILE_PATH: Path = DATA_DIR / "kb.json"
    POLICY_DIR: Path = DATA_DIR / "policies"
    FAISS_DIR: Path = DATA_DIR / "faiss_index"

    # Embedding / FAISS Configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

    # LangSmith Settings
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "true")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "Enterprise-Incident-Resolution-Agent")


    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        if not cls.OPENAI_API_KEY or cls.OPENAI_API_KEY == "your_openai_api_key_here":
            raise ValueError("CRITICAL: OPENAI_API_KEY is not set. Please update your .env file.")


settings = Settings()

# Module-level aliases for consumers that import individual constants directly.
OPENAI_API_KEY = settings.OPENAI_API_KEY
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION
LLM_MODEL = settings.OPENAI_MODEL_NAME
FAISS_DIR = settings.FAISS_DIR
QDRANT_DIR = settings.QDRANT_DIR
QDRANT_COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME
