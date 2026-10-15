"""Self-contained local Farrum Agent Security Demo."""

import os
import sys
import tempfile
from decimal import Decimal

from trusted_execution.config import Policy
from trusted_execution.engine import ExecutionEngine
from trusted_execution.provider import MockProvider


SCENARIOS = (
    {
        "name": "Unauthorized action rejected",
        "action": "charge",
        "amount": "25",
        "current_policy": {
            "allowed_actions": ["refund"],
            "max_amount": "100",
            "auto_approval_limit": "100",
        },
        "expected": "deny",
    },
    {
        "name": "Authorized action executed and verified",
        "action": "refund",
        "amount": "25",
        "current_policy": {
            "allowed_actions": ["refund"],
            "max_amount": "100",
            "auto_approval_limit": "100",
        },
        "expected": "allow",
    },
    {
        "name": "Authorization context changed after approval",
        "action": "refund",
        "amount": "150",
        "current_policy": {
            "allowed_actions": ["refund"],
            "max_amount": "200",
            "auto_approval_limit": "100",
        },
        "expected": "deny",
        "approval_granted": True,
        "policy_after_approval": {
            "allowed_actions": ["refund"],
            "max_amount": "100",
            "auto_approval_limit": "100",
        },
    },
)


class CountingMockProvider(MockProvider):
    """Track actual executions while retaining the independent mock ledger."""

    def __init__(self, db_path):
        super().__init__(db_path)
        self.calls = []

    def execute(self, request_id, action, amount):
        self.calls.append(
            {
                "request_id": request_id,
                "action": action,
                "amount": format(amount, "f"),
            }
        )
        return super().execute(request_id, action, amount)


def _make_policy(data):
    return Policy(
        allowed_actions=set(data["allowed_actions"]),
        max_amount=Decimal(str(data["max_amount"])),
        auto_approval_limit=Decimal(str(data["auto_approval_limit"])),
    )


def _run_scenario(index, scenario):
    evidence = {
        "state": None,
        "provider_calls": [],
        "provider_outcome": None,
        "events": [],
    }
    request_id = "public-demo-{}".format(index)

    with tempfile.TemporaryDirectory(prefix="farrum-agent-demo-") as directory:
        db_path = os.path.join(directory, "history.sqlite3")
        provider = CountingMockProvider(db_path + ".provider.sqlite3")
        engine = ExecutionEngine(
            db_path,
            policy=_make_policy(scenario["current_policy"]),
            provider=provider,
        )
        operation = engine.submit(
            request_id, scenario["action"], Decimal(scenario["amount"])
        )

        if operation.state.value == "pending" and scenario.get(
            "approval_granted", False
        ):
            engine.approve(request_id, approver="demo approval")
            if "policy_after_approval" in scenario:
                engine.policy = _make_policy(scenario["policy_after_approval"])
            operation = engine.execute(request_id)

        evidence["state"] = operation.state.value
        evidence["provider_calls"] = list(provider.calls)
        outcome = provider.verify(request_id)
        if outcome is not None:
            evidence["provider_outcome"] = {
                "state": outcome.state,
                "error": outcome.error,
            }
        evidence["events"] = engine.events(request_id)

    call_count = len(evidence["provider_calls"])
    if call_count == 1 and evidence["state"] == "succeeded":
        actual = "allow"
    elif call_count == 0 and evidence["state"] in {"failed", "pending"}:
        actual = "deny"
    else:
        actual = "unexpected"

    passed = actual == scenario["expected"]
    if scenario["expected"] == "allow":
        passed = passed and call_count == 1 and evidence["state"] == "succeeded"
    else:
        passed = passed and call_count == 0

    return {
        "name": scenario["name"],
        "action": scenario["action"],
        "amount": scenario["amount"],
        "policy": scenario["current_policy"],
        "policy_after_approval": scenario.get("policy_after_approval"),
        "expected": scenario["expected"],
        "actual": actual,
        "passed": passed,
        "evidence": evidence,
    }


def run_demo():
    """Run each bounded scenario with a new temporary history and mock ledger."""
    results = [
        _run_scenario(index, scenario)
        for index, scenario in enumerate(SCENARIOS, start=1)
    ]
    passed = sum(1 for result in results if result["passed"])
    return {
        "title": "Farrum Agent Security Demo",
        "execution_mode": "local simulation; no network or credentials",
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
        },
        "scenarios": results,
    }


def _policy_summary(policy):
    return "allowed_actions={}, max_amount={}, auto_approval_limit={}".format(
        ",".join(policy["allowed_actions"]),
        policy["max_amount"],
        policy["auto_approval_limit"],
    )


def print_report(report, stream=None):
    stream = sys.stdout if stream is None else stream
    print(report["title"], file=stream)
    print("Mode: {}".format(report["execution_mode"]), file=stream)
    print("Provider: local MockProvider (not a real GitHub write)", file=stream)

    for index, result in enumerate(report["scenarios"], start=1):
        evidence = result["evidence"]
        print("\n{}. {}".format(index, result["name"]), file=stream)
        print(
            "   Proposed action: {}(amount={})".format(
                result["action"], result["amount"]
            ),
            file=stream,
        )
        print(
            "   Policy at proposal: {}".format(_policy_summary(result["policy"])),
            file=stream,
        )
        if result["policy_after_approval"] is not None:
            print(
                "   Policy at execution: {}".format(
                    _policy_summary(result["policy_after_approval"])
                ),
                file=stream,
            )

        final_event = evidence["events"][-1] if evidence["events"] else {}
        decision = "ALLOW" if result["actual"] == "allow" else "DENY"
        reason = final_event.get("details")
        print(
            "   Policy decision: {}{}".format(
                decision,
                " - {}".format(reason)
                if decision == "DENY" and reason
                else "",
            ),
            file=stream,
        )
        print(
            "   Protected mock write attempts: {}".format(
                len(evidence["provider_calls"])
            ),
            file=stream,
        )
        outcome = evidence["provider_outcome"]
        verification = (
            "not run (no provider outcome to read back)"
            if outcome is None
            else "verified: {}".format(outcome["state"])
        )
        print("   Read-back verification: {}".format(verification), file=stream)
        print("   Audit evidence:", file=stream)
        for event in evidence["events"]:
            print(
                "     - {}: {}".format(event["state"], event["details"]),
                file=stream,
            )

    summary = report["summary"]
    print(
        "\nResult: {}/{} scenarios passed; {} failed.".format(
            summary["passed"], summary["total"], summary["failed"]
        ),
        file=stream,
    )


def main():
    report = run_demo()
    print_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
