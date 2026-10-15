import os
import sqlite3
from decimal import Decimal
from typing import Tuple

from trusted_execution.models import Operation, OperationState


class InvalidTransition(RuntimeError):
    """Raised when an operation cannot move from its current state."""


class ExecutionStore:
    def __init__(self, db_path):
        self.db_path = os.fspath(db_path)
        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    request_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN (
                            'pending', 'approved', 'executing',
                            'succeeded', 'failed', 'unknown'
                        )
                    ),
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    updated_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    FOREIGN KEY (request_id) REFERENCES executions(request_id)
                );
                """
            )

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _operation(row):
        if row is None:
            return None
        return Operation(
            request_id=row["request_id"],
            action=row["action"],
            amount=Decimal(row["amount"]),
            state=OperationState(row["state"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
        )

    def create(self, request_id, action, amount):
        amount_text = format(amount, "f")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO executions
                    (request_id, action, amount, state)
                VALUES (?, ?, ?, ?)
                """,
                (request_id, action, amount_text, OperationState.PENDING.value),
            )
            created = cursor.rowcount == 1
            if created:
                connection.execute(
                    """
                    INSERT INTO execution_events (request_id, state, details)
                    VALUES (?, ?, ?)
                    """,
                    (request_id, OperationState.PENDING.value, "Request received"),
                )
            row = connection.execute(
                "SELECT * FROM executions WHERE request_id = ?", (request_id,)
            ).fetchone()

        operation = self._operation(row)
        if operation.action != action or operation.amount != amount:
            raise ValueError(
                "Request ID {!r} was already used for a different operation".format(
                    request_id
                )
            )
        return operation, created

    def get(self, request_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM executions WHERE request_id = ?", (request_id,)
            ).fetchone()
        operation = self._operation(row)
        if operation is None:
            raise KeyError("Unknown request ID: {}".format(request_id))
        return operation

    def transition(self, request_id, expected, new_state, details=None, error=None):
        expected_values = [state.value for state in expected]
        if not expected_values:
            raise ValueError("At least one expected state is required")
        placeholders = ", ".join("?" for _ in expected_values)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE executions
                SET state = ?, error = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE request_id = ? AND state IN ({})
                """.format(placeholders),
                [new_state.value, error, request_id] + expected_values,
            )
            if cursor.rowcount != 1:
                current = connection.execute(
                    "SELECT state FROM executions WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if current is None:
                    raise KeyError("Unknown request ID: {}".format(request_id))
                raise InvalidTransition(
                    "Cannot move request {!r} from {} to {}".format(
                        request_id, current["state"], new_state.value
                    )
                )
            connection.execute(
                """
                INSERT INTO execution_events (request_id, state, details)
                VALUES (?, ?, ?)
                """,
                (request_id, new_state.value, details),
            )
            row = connection.execute(
                "SELECT * FROM executions WHERE request_id = ?", (request_id,)
            ).fetchone()
        return self._operation(row)

    def recover_interrupted(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request_id FROM executions WHERE state = ?",
                (OperationState.EXECUTING.value,),
            ).fetchall()
            for row in rows:
                request_id = row["request_id"]
                connection.execute(
                    """
                    UPDATE executions
                    SET state = ?, error = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE request_id = ? AND state = ?
                    """,
                    (
                        OperationState.UNKNOWN.value,
                        "Execution was interrupted; verify the provider outcome",
                        request_id,
                        OperationState.EXECUTING.value,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO execution_events (request_id, state, details)
                    VALUES (?, ?, ?)
                    """,
                    (
                        request_id,
                        OperationState.UNKNOWN.value,
                        "Recovered an interrupted execution; no retry was attempted",
                    ),
                )

    def history(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM executions ORDER BY created_at, request_id"
            ).fetchall()
        return [self._operation(row) for row in rows]

    def events(self, request_id=None):
        query = """
            SELECT request_id, state, details, created_at
            FROM execution_events
        """
        parameters: Tuple[str, ...] = ()
        if request_id is not None:
            query += " WHERE request_id = ?"
            parameters = (request_id,)
        query += " ORDER BY id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
