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
        self._batch_lookup: dict[str, str] = {}
        self._history_path = path or settings.DATA_DIR / "memory_history.json"
        self._load_local_records()

    def _load_local_records(self) -> None:
        if not self._history_path.exists():
            return
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            records = payload.get("records", [])
        else:
            records = payload
        if isinstance(records, list):
            self._test_records = {
                value["memory_id"]: value
                for value in records
                if isinstance(value, dict) and value.get("memory_id")
            }

    def _persist_local_records(self) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": list(self._test_records.values())}
        self._history_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _memory_payload(value: dict[str, Any]) -> str:
        """Keep only the approved corporate or employee history in Mem0."""
        if value.get("record_type") == "batch":
            allowed = {
                "corporate_account",
                "policy_start_date",
                "policy_end_date",
                "opening_cd_balance_inr",
                "net_premium_adjustment_inr",
                "closing_cd_balance_inr",
                "premium_run_rate_inr",
                "monthly_addition_count",
                "monthly_deletion_count",
                "allocated_corporate_buffer_utilization_inr",
            }
        else:
            allowed = {
                "employee_identifier",
                "policy_term",
                "members",
                "dependent_tree",
                "life_event",
                "prior_claims",
                "outside_life_event_window",
            }
        return json.dumps(
            {key: item for key, item in value.items() if key in allowed},
            sort_keys=True,
        )

    @staticmethod
    def batch_id(corporate_account: str, policy_start: date, source_digest: str) -> str:
        value = f"{corporate_account}|{policy_start.isoformat()}|{source_digest}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def record_batch(self, batch_id: str, record: dict[str, Any]) -> bool:
        if batch_id in self._batch_lookup:
            return False
        record_fingerprint = hashlib.sha256(
            json.dumps(record, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        memory_id = f"{MEMORY_NAMESPACE}:term-snapshot:{record_fingerprint}"
        value = {
            "memory_id": memory_id,
            "record_type": "batch",
            **record,
        }
        self._batch_lookup[batch_id] = memory_id
        if self.memory is None:
            if memory_id in self._test_records:
                return False
            self._test_records[memory_id] = value
            self._persist_local_records()
            return True
        if memory_id in self._test_records:
            return False
        self._test_records[memory_id] = value
        self._persist_local_records()
        state_user_id = value.get("state_user_id")
        self.memory.add(
            self._memory_payload(value),
            user_id=state_user_id or memory_id,
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
            values = [
                value
                for value in self._test_records.values()
                if value.get("state_user_id") == state_user_id
            ]
            if not values:
                values = self._decode_memories(self._get_all(state_user_id))

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
            "policy_term": policy_term,
            "members": members,
            "dependent_tree": (record or {}).get("dependent_tree", []),
            "life_event": {
                "action_type": (record or {}).get("action_type"),
                "event_date": (record or {}).get("event_date"),
                "intimation_date": (record or {}).get("intimation_date"),
                "outside_window": (record or {}).get("outside_life_event_window", False),
            },
            "prior_claims": (record or {}).get("prior_claims", []),
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
        employee_user_id = self._employee_user_id(employee_token, policy_term)
        value["employee_user_id"] = employee_user_id
        if self.memory is None:
            if memory_id in self._test_records:
                return False
            self._test_records[memory_id] = value
            self._persist_local_records()
            return True
        if memory_id in self._test_records:
            return False
        self._test_records[memory_id] = value
        self._persist_local_records()
        if state_user_id:
            self.memory.add(self._memory_payload(value), user_id=state_user_id)
        else:
            self.memory.add(self._memory_payload(value), user_id=memory_id)
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
            values = [
                value
                for value in self._test_records.values()
                if value.get("state_user_id") == state_user_id
            ]
            if not values:
                values = self._decode_memories(self._get_all(state_user_id))
        return [value for value in values if value.get("record_type") == "enrollment_change"]

    def get_late_life_event_attempts(
        self, corporate_account: str, policy_start_date: date
    ) -> list[dict[str, Any]]:
        """Return life-event additions rejected outside the policy window."""
        return [
            value
            for value in self.get_enrollment_history(corporate_account, policy_start_date)
            if value.get("outside_life_event_window") is True
        ]

    @staticmethod
    def _employee_user_id(employee_token: str, policy_term: str) -> str:
        value = f"{MEMORY_NAMESPACE}:{policy_term}:{employee_token}"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"{MEMORY_NAMESPACE}:employee-term:{digest}"

    def get_employee_policy_context(
        self,
        employee_token: str,
        corporate_account: str,
        policy_start_date: date,
    ) -> list[dict[str, Any]]:
        """Return one employee's enrolled tree, life events, and claims for a term."""
        policy_term = policy_start_date.isoformat()
        employee_user_id = self._employee_user_id(employee_token, policy_term)
        if self.memory is None:
            values = [
                value
                for value in self._test_records.values()
                if value.get("employee_user_id") == employee_user_id
            ]
        else:
            values = self.get_enrollment_history(
                corporate_account=corporate_account,
                policy_start_date=policy_start_date,
            )
            values = [
                value
                for value in values
                if value.get("employee_user_id") == employee_user_id
            ]
        return [value for value in values if value.get("record_type") == "enrollment_change"]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        memory_id = self._batch_lookup.get(batch_id)
        if memory_id is None:
            return None
        if self.memory is None:
            return self._test_records.get(memory_id)
        memories = self._get_all(memory_id)
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

    def _get_all(self, user_id: str) -> Any:
        """Adapt history reads to the installed Mem0 get_all API."""
        return self.memory.get_all(filters={"user_id": user_id})

    def _has_memory_in_user(self, memory_id: str, user_id: str) -> bool:
        memories = self._get_all(user_id)
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
            self.history = LocalHistoryStore(memory=self.memory)
            logger.info("[MEM0] Memory Service initialized.")
        except Exception as e:
            logger.warning(f"[MEM0] Mem0 initialization notice ({str(e)}). Running in fallback mode.")
            try:
                memory_config["vector_store"]["config"]["on_disk"] = False
                self.memory = Memory.from_config(memory_config)
                self.history = LocalHistoryStore(memory=self.memory)
            except Exception as fallback_error:
                logger.error(f"[MEM0] Fallback initialization failed ({str(fallback_error)}). Memory disabled.")
                self.memory = None
                self.history = LocalHistoryStore()
 
    def get_user_memories(self, user_id: str) -> List[str]:
        if self.memory is None:
            return []
        try:
            results = self.history._get_all(user_id)
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
