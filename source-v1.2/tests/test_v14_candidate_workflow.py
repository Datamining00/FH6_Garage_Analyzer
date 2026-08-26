from __future__ import annotations

import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "validate-v1.4-architecture-candidates.yml"
)


class V14CandidateWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_or_architecture_branch_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.source)
        self.assertIn("\n  push:", self.source)
        self.assertIn("v1.4.0-alpha.1-architecture-refactor", self.source)
        self.assertNotIn("\n      - main", self.source)
        self.assertNotIn("\n  release:", self.source)

    def test_complete_windows_regression_precedes_build(self) -> None:
        self.assertIn('python-version: ["3.12", "3.13"]', self.source)
        self.assertIn("python -m unittest discover -s tests -v", self.source)
        self.assertIn("needs: windows-regression", self.source)

    def test_all_three_candidates_are_executed_or_uploaded(self) -> None:
        for label in ("Standard", "Portable", "Source"):
            self.assertIn(f"Execute {label} with graceful shutdown", self.source)
            self.assertIn(f"Upload {label} candidate", self.source)

    def test_workflow_does_not_publish_a_release(self) -> None:
        self.assertNotIn("softprops/action-gh-release", self.source)
        self.assertNotIn("gh release", self.source)
        self.assertNotIn("contents: write", self.source)


if __name__ == "__main__":
    unittest.main()
