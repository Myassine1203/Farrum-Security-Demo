import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from trusted_execution.public_demo import main, run_demo


class FarrumPublicDemoTests(unittest.TestCase):
    def test_three_scenarios_prove_decisions_and_provider_outcomes(self):
        with patch("urllib.request.urlopen") as open_url:
            report = run_demo()

        self.assertEqual(
            report["summary"], {"total": 3, "passed": 3, "failed": 0}
        )
        self.assertEqual(
            [item["actual"] for item in report["scenarios"]],
            ["deny", "allow", "deny"],
        )
        denied, allowed, regression = report["scenarios"]
        self.assertEqual(denied["evidence"]["provider_calls"], [])
        self.assertEqual(len(allowed["evidence"]["provider_calls"]), 1)
        self.assertEqual(
            allowed["evidence"]["provider_outcome"]["state"], "succeeded"
        )
        self.assertEqual(regression["evidence"]["provider_calls"], [])
        self.assertIn(
            "exceeds the configured maximum",
            regression["evidence"]["events"][-1]["details"],
        )
        self.assertTrue(
            all(item["evidence"]["events"] for item in report["scenarios"])
        )
        open_url.assert_not_called()

    def test_console_report_includes_audit_evidence_and_mock_disclaimer(self):
        output = StringIO()
        with patch("urllib.request.urlopen") as open_url, redirect_stdout(output):
            exit_code = main()

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Farrum Agent Security Demo", text)
        self.assertIn("Proposed action: charge(amount=25)", text)
        self.assertIn("Policy decision: DENY", text)
        self.assertIn("Protected mock write attempts: 0", text)
        self.assertIn("Protected mock write attempts: 1", text)
        self.assertIn("Read-back verification: verified: succeeded", text)
        self.assertIn("Audit evidence:", text)
        self.assertIn("not a real GitHub write", text)
        open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
