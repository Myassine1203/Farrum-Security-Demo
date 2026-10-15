from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class OperationState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Operation:
    request_id: str
    action: str
    amount: Decimal
    state: OperationState
    created_at: str
    updated_at: str
    error: Optional[str] = None
