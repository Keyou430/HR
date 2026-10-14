"""Explicit process-local actors for narrowly scoped background operations.

HTTP payloads are never converted into these actors. They grant no generic
resource scope and are accepted only by the declared internal operations.
"""

from enum import Enum, auto

from fastapi import HTTPException


class SystemActor(Enum):
    OVERDUE_SCANNER = auto()
    ROLE_NOTIFIER = auto()


def require_system_actor(actor: object, *allowed: SystemActor) -> None:
    if not any(actor is expected for expected in allowed):
        raise HTTPException(status_code=403, detail="未声明合法的系统任务身份")
