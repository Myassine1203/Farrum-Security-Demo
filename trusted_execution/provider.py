import os
import sqlite3
from dataclasses import dataclass
from typing import Optional


class ProviderTimeout(TimeoutError):
    """A simulated timeout where the external outcome may be uncertain."""


@dataclass(frozen=True)
class ProviderOutcome:
    state: str
    error: Optional[str] = None


class MockProvider:
    """A local fake provider with its own independently queried SQLite ledger."""

    BEHAVIORS = {"success", "failure", "timeout-before", "timeout-after"}

    def __init__(self, db_path):
        self.db_path = os.fspath(db_path)
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_outcomes (
                    request_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('succeeded', 'failed')),
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                );
                CREATE TABLE IF NOT EXISTS provider_behaviors (
                    request_id TEXT PRIMARY KEY,
                    behavior TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(provider_outcomes)"
                )
            }
            if "action" not in columns:
                connection.execute(
                    "ALTER TABLE provider_outcomes "
                    "ADD COLUMN action TEXT NOT NULL DEFAULT ''"
                )
            if "amount" not in columns:
                connection.execute(
                    "ALTER TABLE provider_outcomes "
                    "ADD COLUMN amount TEXT NOT NULL DEFAULT ''"
                )

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def set_behavior(self, request_id, behavior):
        if behavior not in self.BEHAVIORS:
            raise ValueError(
                "Unsupported provider behavior {!r}; choose from {}".format(
                    behavior, ", ".join(sorted(self.BEHAVIORS))
                )
            )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO provider_behaviors (request_id, behavior)
                VALUES (?, ?)
                ON CONFLICT(request_id) DO UPDATE SET behavior = excluded.behavior
                """,
                (request_id, behavior),
            )

    def execute(self, request_id, action, amount):
        timeout = False
        amount_text = format(amount, "f")
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT action, amount, state, error
                FROM provider_outcomes WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if existing is not None:
                if existing["action"] and (
                    existing["action"] != action
                    or existing["amount"] != amount_text
                ):
                    raise ValueError(
                        "Provider request ID was reused with different details"
                    )
                return ProviderOutcome(existing["state"], existing["error"])

            behavior_row = connection.execute(
                "SELECT behavior FROM provider_behaviors WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            behavior = behavior_row["behavior"] if behavior_row else "success"
            connection.execute(
                "DELETE FROM provider_behaviors WHERE request_id = ?", (request_id,)
            )

            if behavior == "timeout-before":
                timeout = True
            else:
                if behavior == "failure":
                    outcome = ProviderOutcome(
                        "failed", "Simulated external API failure"
                    )
                else:
                    outcome = ProviderOutcome("succeeded")
                connection.execute(
                    """
                    INSERT INTO provider_outcomes
                        (request_id, action, amount, state, error)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        action,
                        amount_text,
                        outcome.state,
                        outcome.error,
                    ),
                )
                if behavior == "timeout-after":
                    timeout = True

        if timeout:
            raise ProviderTimeout("Simulated provider timeout")
        return outcome

    def verify(self, request_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, error FROM provider_outcomes WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return ProviderOutcome(row["state"], row["error"])
