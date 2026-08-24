# services/memory_service.py
 
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, List, Optional
from mem0 import Memory
from config.settings import settings
from utils.logger import logger

# Dedicated on-disk path so this app's local Qdrant store never collides with
# other processes/tools that use mem0's shared default of /tmp/qdrant.
LOCAL_VECTOR_STORE_PATH = str(settings.DATA_DIR / ".mem0_qdrant")
MEMORY_NAMESPACE = "gmc-history"


class LocalHistoryStore:
    """Mem0-backed durable store for policy-term and census history."""

    def __init__(self, memory: Memory | None = None, path: Path | None = None):
        if isinstance(memory, Path):
            path = memory
            memory = None
        self.memory = memory
        self._test_records: dict[str, dict[str, Any]] = {}
        self._test_path = path

    @staticmethod
    def batch_id(corporate_account: str, policy_start: date, source_digest: str) -> str:
        value = f"{corporate_account}|{policy_start.isoformat()}|{source_digest}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def record_batch(self, batch_id: str, record: dict[str, Any]) -> bool:
        memory_id = f"{MEMORY_NAMESPACE}:batch:{batch_id}"
        value = {
            "memory_id": memory_id,
            "record_type": "batch",
            "batch_id": batch_id,
            **record,
        }
        if self.memory is None:
            if memory_id in self._test_records:
                return False
            self._test_records[memory_id] = value
            return True
        if self._has_memory(memory_id):
            return False
        self.memory.add(
            json.dumps(value, sort_keys=True),
            user_id=memory_id,
        )
        state_user_id = value.get("state_user_id")
        if state_user_id and not self._has_memory_in_user(value["memory_id"], state_user_id):
            self.memory.add(
                json.dumps(value, sort_keys=True),
                user_id=state_user_id,
            )
        return True

    def get_latest_batch(
        self, corporate_account: str, policy_start_date: date
    ) -> dict[str, Any] | None:
        """Return the latest stored policy-term state for an account."""
        state_user_id = self._state_user_id(corporate_account, policy_start_date)
        if self.memory is None:
            values = [
                value
                for value in self._test_records.values()
                if value.get("state_user_id") == state_user_id
            ]
        else:
            values = self._decode_memories(self.memory.get_all(user_id=state_user_id))

        values = [value for value in values if value.get("record_type") == "batch"]
        values.sort(key=lambda value: value.get("endorsement_effective_date", ""))
        return values[-1] if values else None

    @staticmethod
    def _state_user_id(corporate_account: str, policy_start_date: date) -> str:
        term = f"{corporate_account}|{policy_start_date.isoformat()}"
        digest = hashlib.sha256(term.encode("utf-8")).hexdigest()[:16]
        return f"{MEMORY_NAMESPACE}:term:{digest}"

    @staticmethod
    def _decode_memories(memories: Any) -> list[dict[str, Any]]:
        items = memories if isinstance(memories, list) else memories.get("results", [])
        values = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                value = json.loads(item.get("memory", "{}"))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                values.append(value)
        return values

    def record_enrollment(
        self,
        employee_token: str,
        policy_term: str,
        members: list[str],
        record: dict[str, Any] | None = None,
    ) -> bool:
        record_id = hashlib.sha256(
            f"{policy_term}:{employee_token}:{json.dumps(record or {}, sort_keys=True)}".encode("utf-8")
        ).hexdigest()
        memory_id = f"{MEMORY_NAMESPACE}:enrollment:{record_id}"
        value = {
            "memory_id": memory_id,
            "record_type": "enrollment_change",
            "employee_identifier": employee_token,
            "employee_token": employee_token,
            "policy_term": policy_term,
            "members": members,
            **(record or {}),
        }
        state_user_id = None
        corporate_account = value.get("corporate_account")
        if corporate_account:
            state_user_id = self._state_user_id(
                corporate_account,
                date.fromisoformat(policy_term),
            )
            value["state_user_id"] = state_user_id
        if self.memory is None:
            if memory_id in self._test_records:
                return False
            self._test_records[memory_id] = value
            return True
        if self._has_memory(memory_id):
            return False
        self.memory.add(json.dumps(value, sort_keys=True), user_id=memory_id)
        if state_user_id and not self._has_memory_in_user(memory_id, state_user_id):
            self.memory.add(json.dumps(value, sort_keys=True), user_id=state_user_id)
        return True

    def get_enrollment_history(
        self, corporate_account: str, policy_start_date: date
    ) -> list[dict[str, Any]]:
        """Return enrollment changes recorded for one policy term."""
        state_user_id = self._state_user_id(corporate_account, policy_start_date)
        if self.memory is None:
            values = [
                value
                for value in self._test_records.values()
                if value.get("state_user_id") == state_user_id
            ]
        else:
            values = self._decode_memories(self.memory.get_all(user_id=state_user_id))
        return [value for value in values if value.get("record_type") == "enrollment_change"]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        memory_id = f"{MEMORY_NAMESPACE}:batch:{batch_id}"
        if self.memory is None:
            return self._test_records.get(memory_id)
        memories = self.memory.get_all(user_id=memory_id)
        for item in memories if isinstance(memories, list) else memories.get("results", []):
            text = item.get("memory", "") if isinstance(item, dict) else ""
            try:
                value = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                continue
            if value.get("memory_id") == memory_id:
                return value
        return None

    def _has_memory(self, memory_id: str) -> bool:
        if self.memory is None:
            return memory_id in self._test_records
        return self._has_memory_in_user(memory_id, memory_id)

    def _has_memory_in_user(self, memory_id: str, user_id: str) -> bool:
        memories = self.memory.get_all(user_id=user_id)
        items = memories if isinstance(memories, list) else memories.get("results", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                if json.loads(item.get("memory", "{}")).get("memory_id") == memory_id:
                    return True
            except (TypeError, json.JSONDecodeError):
                continue
        return False


class Mem0Service:
    def __init__(self):
        self.memory: Optional[Memory] = None
        self.history = LocalHistoryStore()
        try:
            memory_config = {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": settings.OPENAI_MODEL_NAME,
                        "api_key": settings.OPENAI_API_KEY,
                    },
                },
                "vector_store": {
                    "provider": "qdrant",
                    "config": {"path": LOCAL_VECTOR_STORE_PATH},
                },
            }
            if settings.MEM0_API_KEY:
                self.memory = Memory.from_config({"api_key": settings.MEM0_API_KEY})
            else:
                self.memory = Memory.from_config(memory_config)
            logger.info("[MEM0] Memory Service initialized.")
        except Exception as e:
            logger.warning(f"[MEM0] Mem0 initialization notice ({str(e)}). Running in fallback mode.")
            try:
                memory_config["vector_store"]["config"]["on_disk"] = False
                self.memory = Memory.from_config(memory_config)
            except Exception as fallback_error:
                logger.error(f"[MEM0] Fallback initialization failed ({str(fallback_error)}). Memory disabled.")
                self.memory = None
 
    def get_user_memories(self, user_id: str) -> List[str]:
        if self.memory is None:
            return []
        try:
            results = self.memory.get_all(user_id=user_id)
            memories = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and "memory" in item:
                        memories.append(item["memory"])
            elif isinstance(results, dict) and "results" in results:
                memories = [m.get("memory", "") for m in results.get("results", [])]
            return memories
        except Exception as e:
            logger.error(f"[MEM0] Failed to fetch memories: {str(e)}")
            return []
 
    def add_user_memory(self, user_id: str, interaction: str) -> bool:
        if self.memory is None:
            return False
        try:
            self.memory.add(interaction, user_id=user_id)
            return True
        except Exception as e:
            logger.error(f"[MEM0] Failed to save memory: {str(e)}")
            return False
 
    def close(self):
        """Safely close underlying vector store connections if present."""
        if self.memory is None:
            return
        try:
            if hasattr(self.memory, "vector_store") and hasattr(self.memory.vector_store, "client"):
                if hasattr(self.memory.vector_store.client, "close"):
                    self.memory.vector_store.client.close()
        except Exception:
            pass
 
 
mem0_service = Mem0Service()
