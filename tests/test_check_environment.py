from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_environment as checks


class EnvironmentOptionsTests(unittest.TestCase):
    def test_core_does_not_schedule_source_or_notebook_access(self):
        args = checks.parse_arguments([])
        planned = dict(checks.build_checks(Path("unused"), args))
        for name in ("source_selection", "real_sample", "notebook_execution"):
            self.assertIsNone(planned[name])
        self.assertFalse(args.with_data)

    def test_notebook_enables_data_and_accepts_custom_kernel(self):
        args = checks.parse_arguments(["--with-notebook", "--kernel", "team-linux"])
        self.assertTrue(args.with_data)
        self.assertEqual(args.kernel, "team-linux")

    def test_core_success_does_not_claim_full_verification(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            planned = [("fixture", lambda: {"rows": 3}), ("real_sample", None)]
            with patch.object(checks, "build_checks", return_value=planned), redirect_stdout(StringIO()):
                result = checks.main(["--work-dir", tmp])
            report = json.loads((Path(tmp) / "environment-report.json").read_text())
            self.assertEqual(result, 0)
            self.assertTrue(report["ready"])
            self.assertFalse(report["full_verification"])
            self.assertEqual(report["scope"], "core")
            self.assertEqual(report["checks"][1]["status"], "skipped")

    def test_required_failure_writes_report_and_returns_nonzero(self):
        def fail():
            raise ValueError("Intentional missing dependency")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            with patch.object(checks, "build_checks", return_value=[("dependency", fail)]), redirect_stdout(StringIO()):
                result = checks.main(["--work-dir", tmp])
            report = json.loads((Path(tmp) / "environment-report.json").read_text())
            self.assertEqual(result, 1)
            self.assertFalse(report["ready"])
            self.assertFalse(report["full_verification"])
            self.assertIn("Intentional missing dependency", report["checks"][0]["error"])


if __name__ == "__main__":
    unittest.main()
