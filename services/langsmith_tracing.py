from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from config.settings import settings
from utils.logger import logger


class BatchTrace:
    """Best-effort nested LangSmith trace for one anonymized endorsement batch."""

    def __init__(self, batch_id: str, corporate_account: str, policy_start: str):
        self.enabled = (
            settings.LANGCHAIN_TRACING_V2.lower() == "true"
            and bool(settings.LANGCHAIN_API_KEY)
        )
        self.root = None
        self.batch_id = batch_id
        if not self.enabled:
            return
        try:
            from langsmith.run_trees import RunTree

            self.root = RunTree(
                name="gmc_endorsement_batch",
                run_type="chain",
                project_name=settings.LANGCHAIN_PROJECT,
                inputs={"batch_id": batch_id},
                tags=["gmc", "endorsement", "batch"],
                extra={
                    "metadata": {
                        "batch_id": batch_id,
                        "corporate_account": corporate_account,
                        "policy_start": policy_start,
                    }
                },
            )
            self.root.post(exclude_child_runs=True)
        except Exception as error:
            logger.warning(f"[LANGSMITH] Tracing disabled for batch ({type(error).__name__}).")
            self.enabled = False
            self.root = None

    @contextmanager
    def stage(self, name: str, inputs: dict[str, Any] | None = None) -> Iterator[Any]:
        if not self.root:
            yield None
            return
        child = self.root.create_child(
            name=name,
            run_type="chain",
            inputs=inputs or {},
            tags=["gmc", "endorsement", name],
        )
        try:
            child.post()
            yield child
        except Exception as error:
            try:
                child.end(error=str(error))
                child.post()
            except Exception:
                pass
            raise
        else:
            child.end(outputs={"status": "completed"})
            try:
                child.post()
            except Exception:
                pass

    def finish(self, status: str, **metadata: Any) -> None:
        if not self.root:
            return
        try:
            self.root.end(
                outputs={"status": status},
                metadata={"batch_id": self.batch_id, **metadata},
            )
            self.root.post(exclude_child_runs=False)
        except Exception as error:
            logger.warning(f"[LANGSMITH] Could not finalize trace ({type(error).__name__}).")
