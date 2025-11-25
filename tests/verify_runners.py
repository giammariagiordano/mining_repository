import json
import unittest
from unittest.mock import patch, MagicMock
from analyzers.bandit_runner import run_bandit_and_collect_vulns
from analyzers.deadcode_runner import run_vulture_and_collect_deadcode

class TestRunners(unittest.TestCase):
    def test_bandit_runner(self):
        # Mock subprocess.run for Bandit
        with patch('subprocess.run') as mock_run:
            # Simulate Bandit JSON output
            bandit_output = {
                "results": [
                    {
                        "filename": "vuln.py",
                        "line_number": 123,
                        "test_id": "B101",
                        "issue_text": "Use of assert detected.",
                        "issue_severity": "LOW",
                        "issue_confidence": "HIGH"
                    }
                ]
            }
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=json.dumps(bandit_output),
                stderr=""
            )

            metrics = run_bandit_and_collect_vulns("/dummy/path", bandit_binary="bandit")

            self.assertIn("vuln_details", metrics)
            vuln_details = json.loads(metrics["vuln_details"])
            self.assertEqual(len(vuln_details), 1)
            self.assertEqual(vuln_details[0]["filename"], "vuln.py")
            self.assertEqual(vuln_details[0]["line_number"], 123)
            self.assertEqual(vuln_details[0]["test_id"], "B101")
            self.assertEqual(vuln_details[0]["issue_text"], "Use of assert detected.")
            self.assertEqual(vuln_details[0]["issue_severity"], "LOW")
            self.assertEqual(vuln_details[0]["issue_confidence"], "HIGH")

    def test_vulture_runner_json(self):
        # Mock subprocess.run for Vulture (JSON mode)
        with patch('subprocess.run') as mock_run:
            # Simulate Vulture JSON output
            vulture_output = [
                {
                    "type": "function",
                    "name": "unused_func",
                    "filename": "dead.py",
                    "lineno": 42,
                    "confidence": 100
                }
            ]
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=json.dumps(vulture_output),
                stderr=""
            )

            metrics = run_vulture_and_collect_deadcode("/dummy/path", vulture_binary="vulture")

            self.assertIn("deadcode_details", metrics)
            deadcode_details = json.loads(metrics["deadcode_details"])
            self.assertEqual(len(deadcode_details), 1)
            self.assertEqual(deadcode_details[0]["type"], "function")
            self.assertEqual(deadcode_details[0]["name"], "unused_func")
            self.assertEqual(deadcode_details[0]["filename"], "dead.py")
            self.assertEqual(deadcode_details[0]["lineno"], 42)
            self.assertEqual(deadcode_details[0]["confidence"], 100)

if __name__ == '__main__':
    unittest.main()
