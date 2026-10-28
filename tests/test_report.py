"""Synthetic contract checks for the report model; no project data is read."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ml_experiment_preflight.report import (
    RULE_IDS, ReportValidationError, build_report, exit_code, validate_report,
)


def clear_results():
    return [{
        "rule_id": rule_id, "status": "pass", "severity": "none",
        "coverage_complete": True, "reason_code": None,
        "unknown_refs": [], "evidence": [],
    } for rule_id in RULE_IDS]


class ReportTests(unittest.TestCase):
    def test_clear_warning_critical_and_incomplete_aggregation(self):
        cases = [
            (None, "clear", 0, 0, 0),
            ("warning", "review", 1, 1, 0),
            ("critical", "blocked", 1, 1, 0),
        ]
        for severity, expected_status, expected_exit, findings, unknowns in cases:
            with self.subTest(severity=severity):
                rows = clear_results()
                if severity:
                    index = 3 if severity == "critical" else 1
                    code = "INPUT_MISSING" if severity == "critical" else "ENTRY_CHANGED"
                    ref = "input:1" if severity == "critical" else "entry"
                    rows[index].update(status="finding", severity=severity,
                                       evidence=[{"code": code, "refs": [ref]}])
                report = build_report(rows, input_count=1, output_count=1)
                self.assertEqual(report["overall"], {
                    "status": expected_status, "finding_count": findings,
                    "unknown_count": unknowns,
                })
                self.assertEqual(exit_code(report), expected_exit)

        rows = clear_results()
        rows[4].update(status="unknown", coverage_complete=False,
                       reason_code="OUTPUT_PARENT_UNKNOWN", unknown_refs=["output:1"])
        report = build_report(rows, input_count=1, output_count=1)
        self.assertEqual(report["overall"]["status"], "incomplete")
        self.assertEqual(exit_code(report), 2)

    def test_finding_and_unknown_can_coexist_and_critical_keeps_priority(self):
        rows = clear_results()
        rows[1].update(status="finding", severity="warning", coverage_complete=False,
                       reason_code="GIT_TIMEOUT", unknown_refs=["entry"],
                       evidence=[{"code": "ENTRY_CHANGED", "refs": ["entry"]}])
        rows[4].update(status="unknown", coverage_complete=False,
                       reason_code="OUTPUT_PARENT_UNKNOWN", unknown_refs=["output:1"])
        report = build_report(rows, input_count=1, output_count=1)
        self.assertEqual(report["overall"], {
            "status": "incomplete", "finding_count": 1, "unknown_count": 2,
        })
        self.assertEqual(exit_code(report), 2)
        rows[5].update(status="finding", severity="critical",
                       evidence=[{"code": "OUTPUT_EQUALS_INPUT_OR_ENTRY",
                                  "refs": ["output:1", "input:1"]}])
        report = build_report(rows, input_count=1, output_count=1)
        self.assertEqual(report["overall"]["status"], "blocked")
        self.assertEqual(report["overall"]["unknown_count"], 2)
        self.assertEqual(exit_code(report), 2)

    def test_rejects_duplicate_missing_or_reordered_rule_ids(self):
        for change in ("duplicate", "missing", "reordered"):
            with self.subTest(change=change):
                rows = clear_results()
                if change == "duplicate":
                    rows[1]["rule_id"] = rows[0]["rule_id"]
                elif change == "missing":
                    rows.pop()
                else:
                    rows[0], rows[1] = rows[1], rows[0]
                with self.assertRaises(ReportValidationError):
                    build_report(rows, input_count=1, output_count=1)

    def test_rejects_illegal_status_severity_coverage_combinations(self):
        mutations = [
            {"status": "pass", "severity": "warning"},
            {"status": "pass", "reason_code": "GIT_TIMEOUT"},
            {"status": "pass", "coverage_complete": False,
             "reason_code": "GIT_TIMEOUT", "unknown_refs": ["root"]},
            {"status": "unknown", "coverage_complete": True},
            {"status": "unknown", "coverage_complete": False,
             "unknown_refs": ["entry"]},
            {"status": "finding", "severity": "none",
             "evidence": [{"code": "ENTRY_CHANGED", "refs": ["entry"]}]},
            {"status": "finding", "severity": "warning"},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                rows = clear_results()
                rows[1].update(mutation)
                with self.assertRaises(ReportValidationError):
                    build_report(rows, input_count=1, output_count=1)

    def test_finding_severity_must_match_its_rule_evidence(self):
        rows = clear_results()
        rows[1].update(status="finding", severity="critical",
                       evidence=[{"code": "ENTRY_CHANGED", "refs": ["entry"]}])
        with self.assertRaises(ReportValidationError):
            build_report(rows, input_count=1, output_count=1)
        rows[1]["severity"] = "warning"
        rows[4].update(status="finding", severity="critical",
                       evidence=[{"code": "OUTPUT_TYPE_MISMATCH", "refs": ["output:1"]}])
        self.assertEqual(build_report(rows, input_count=1, output_count=1)
                         ["overall"]["status"], "blocked")

    def test_invalid_results_container_raises_contract_error(self):
        with self.assertRaises(ReportValidationError):
            build_report("invalid", input_count=1, output_count=1)

    def test_rejects_wrong_json_fields_types_counts_and_overall(self):
        report = build_report(clear_results(), input_count=1, output_count=1)
        bad_reports = []
        for mutation in (
            lambda r: r.update(extra="leak"),
            lambda r: r["scope"].update(input_count=True),
            lambda r: r["results"][0].update(reason_code="C:\\private\\name"),
            lambda r: r["overall"].update(finding_count=1),
            lambda r: r["overall"].update(status="blocked"),
        ):
            altered = copy.deepcopy(report)
            mutation(altered)
            bad_reports.append(altered)
        for altered in bad_reports:
            with self.subTest(altered=altered):
                with self.assertRaises(ReportValidationError):
                    validate_report(altered)


if __name__ == "__main__":
    unittest.main()
