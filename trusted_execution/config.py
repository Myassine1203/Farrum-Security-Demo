from dataclasses import dataclass, field
from decimal import Decimal
from typing import Set


class PolicyViolation(ValueError):
    """Raised when an operation is not permitted by the configured policy."""


@dataclass
class Policy:
    allowed_actions: Set[str] = field(default_factory=lambda: {"refund"})
    max_amount: Decimal = Decimal("1000")
    auto_approval_limit: Decimal = Decimal("100")

    def __post_init__(self):
        self.max_amount = Decimal(str(self.max_amount))
        self.auto_approval_limit = Decimal(str(self.auto_approval_limit))
        self.validate_configuration()

    def validate_configuration(self):
        if not isinstance(self.allowed_actions, set) or any(
            not isinstance(action, str) or not action.strip()
            for action in self.allowed_actions
        ):
            raise ValueError("allowed_actions must be a set of non-empty strings")
        if not isinstance(self.max_amount, Decimal):
            raise ValueError("max_amount must be a Decimal value")
        if not isinstance(self.auto_approval_limit, Decimal):
            raise ValueError("auto_approval_limit must be a Decimal value")
        if not self.max_amount.is_finite() or self.max_amount <= 0:
            raise ValueError("max_amount must be a finite positive amount")
        if not self.auto_approval_limit.is_finite() or self.auto_approval_limit < 0:
            raise ValueError(
                "auto_approval_limit must be a finite non-negative amount"
            )
        if self.auto_approval_limit > self.max_amount:
            raise ValueError("auto_approval_limit cannot exceed max_amount")

    def validate(self, action, amount):
        self.validate_configuration()
        if action not in self.allowed_actions:
            raise PolicyViolation("Action is not permitted: {}".format(action))
        if not amount.is_finite() or amount <= 0:
            raise PolicyViolation("Amount must be a finite positive value")
        if amount > self.max_amount:
            raise PolicyViolation(
                "Amount exceeds the configured maximum of {}".format(
                    self.max_amount
                )
            )

    def requires_approval(self, amount):
        return amount > self.auto_approval_limit
