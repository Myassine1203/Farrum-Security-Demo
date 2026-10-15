from decimal import Decimal, InvalidOperation

from trusted_execution.config import Policy, PolicyViolation
from trusted_execution.models import OperationState
from trusted_execution.provider import MockProvider, ProviderTimeout
from trusted_execution.store import ExecutionStore


class ExecutionEngine:
    def __init__(self, db_path, policy=None, provider=None):
        self.store = ExecutionStore(db_path)
        provider_path = "{}.provider.sqlite3".format(db_path)
        self.provider = provider or MockProvider(provider_path)
        self.policy = policy or Policy()
        self.store.recover_interrupted()

    @staticmethod
    def _amount(value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("Amount must be a valid decimal number")
        if not amount.is_finite():
            raise ValueError("Amount must be finite")
        return amount

    def submit(self, request_id, action, amount):
        if not request_id or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not action or not action.strip():
            raise ValueError("action must not be empty")

        decimal_amount = self._amount(amount)
        operation, created = self.store.create(
            request_id, action, decimal_amount
        )
        if not created:
            return operation

        try:
            self.policy.validate(action, decimal_amount)
        except PolicyViolation as error:
            return self.store.transition(
                request_id,
                [OperationState.PENDING],
                OperationState.FAILED,
                details=str(error),
                error=str(error),
            )

        if self.policy.requires_approval(decimal_amount):
            return operation

        self.store.transition(
            request_id,
            [OperationState.PENDING],
            OperationState.APPROVED,
            details="Automatically approved within the configured limit",
        )
        return self.execute(request_id)

    def approve(self, request_id, approver="simulated human"):
        operation = self.store.get(request_id)
        if operation.state != OperationState.PENDING:
            raise ValueError(
                "Only pending operations can be approved (current state: {})".format(
                    operation.state.value
                )
            )
        self.policy.validate(operation.action, operation.amount)
        if not approver or not approver.strip():
            raise ValueError("approver must not be empty")
        return self.store.transition(
            request_id,
            [OperationState.PENDING],
            OperationState.APPROVED,
            details="Approved by {}".format(approver),
        )

    def execute(self, request_id):
        operation = self.store.get(request_id)
        if operation.state != OperationState.APPROVED:
            return operation

        try:
            policy = self.policy
            if not isinstance(policy, Policy):
                raise PolicyViolation("Execution policy is invalid or unavailable")
            Policy.validate(policy, operation.action, operation.amount)
        except Exception as error:
            message = "Execution denied because policy validation failed: {}".format(
                error
            )
            return self.store.transition(
                request_id,
                [OperationState.APPROVED],
                OperationState.FAILED,
                details=message,
                error=message,
            )

        self.store.transition(
            request_id,
            [OperationState.APPROVED],
            OperationState.EXECUTING,
            details="Mock-provider request started",
        )
        try:
            outcome = self.provider.execute(
                request_id, operation.action, operation.amount
            )
        except ProviderTimeout as error:
            return self.store.transition(
                request_id,
                [OperationState.EXECUTING],
                OperationState.UNKNOWN,
                details="Provider timed out; verification is required",
                error=str(error),
            )

        final_state = OperationState(outcome.state)
        details = (
            "Mock provider confirmed success"
            if final_state == OperationState.SUCCEEDED
            else "Mock provider reported failure"
        )
        return self.store.transition(
            request_id,
            [OperationState.EXECUTING],
            final_state,
            details=details,
            error=outcome.error,
        )

    def verify(self, request_id):
        operation = self.store.get(request_id)
        if operation.state != OperationState.UNKNOWN:
            return operation

        outcome = self.provider.verify(request_id)
        if outcome is None:
            return operation

        verified_state = OperationState(outcome.state)
        details = (
            "Independent provider verification confirmed success"
            if verified_state == OperationState.SUCCEEDED
            else "Independent provider verification confirmed failure"
        )
        return self.store.transition(
            request_id,
            [OperationState.UNKNOWN],
            verified_state,
            details=details,
            error=outcome.error,
        )

    def get(self, request_id):
        return self.store.get(request_id)

    def history(self):
        return self.store.history()

    def events(self, request_id=None):
        return self.store.events(request_id)
