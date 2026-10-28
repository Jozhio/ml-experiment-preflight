"""Version 1 report validation and aggregation, independent of rule execution."""

import re

from . import __version__


RULE_IDS = ("GIT-001", "GIT-002", "GIT-003", "PATH-001", "OUT-001", "OUT-002")
FINDING_CODES = {
    "GIT-001": {"NO_REPOSITORY", "NO_HEAD"},
    "GIT-002": {"ENTRY_CHANGED"},
    "GIT-003": {"ENTRY_NOT_TRACKED"},
    "PATH-001": {"ENTRY_MISSING", "INPUT_MISSING", "TYPE_MISMATCH", "ENTRY_ESCAPES_ROOT"},
    "OUT-001": {"OUTPUT_EXISTS", "OUTPUT_TYPE_MISMATCH"},
    "OUT-002": {"OUTPUT_EQUALS_INPUT_OR_ENTRY", "OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT",
                "OUTPUT_INSIDE_INPUT_DIR"},
}
CRITICAL_CODES = {
    "ENTRY_MISSING", "INPUT_MISSING", "TYPE_MISMATCH", "ENTRY_ESCAPES_ROOT",
    "OUTPUT_TYPE_MISMATCH", "OUTPUT_EQUALS_INPUT_OR_ENTRY",
    "OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT",
}
PASS_CODES = {
    "GIT-001": {"REPOSITORY_WITH_HEAD"},
    "GIT-002": {"ENTRY_UNCHANGED"},
    "GIT-003": {"ENTRY_TRACKED"},
    "PATH-001": {"INPUTS_PRESENT_AND_TYPED"},
    "OUT-001": {"OUTPUT_ABSENT_PARENT_KNOWN"},
    "OUT-002": {"NO_OUTPUT_OVERLAP"},
}
UNKNOWN_CODES = {
    "GIT-001": {"GIT_UNAVAILABLE", "GIT_ROOT_MISMATCH", "UNSUPPORTED_GIT_LAYOUT",
                "GIT_TIMEOUT", "GIT_ERROR"},
    "GIT-002": {"ENTRY_UNAVAILABLE", "ENTRY_NOT_TRACKED", "GIT_ENTRY_FLAG_UNSUPPORTED",
                "GIT_CONTEXT_UNKNOWN", "GIT_TIMEOUT", "GIT_ERROR", "GIT_OUTPUT_LIMIT"},
    "GIT-003": {"ENTRY_UNAVAILABLE", "GIT_CONTEXT_UNKNOWN", "GIT_TIMEOUT", "GIT_ERROR"},
    "PATH-001": {"PERMISSION_DENIED", "SYMLINK_UNRESOLVED", "PATH_IO_ERROR",
                 "EVIDENCE_LIMIT"},
    "OUT-001": {"OUTPUT_PARENT_UNKNOWN", "SYMLINK_UNRESOLVED", "PERMISSION_DENIED",
                "PATH_IO_ERROR"},
    "OUT-002": {"PATH_COMPARISON_UNKNOWN", "SYMLINK_UNRESOLVED",
                "OUTPUT_PARENT_UNKNOWN", "EVIDENCE_LIMIT"},
}
RESULT_FIELDS = {"rule_id", "status", "severity", "coverage_complete", "reason_code",
                 "unknown_refs", "evidence"}


class ReportValidationError(ValueError):
    """A report violates the frozen v1 contract."""


def _require(condition: bool) -> None:
    if not condition:
        raise ReportValidationError("invalid report")


def _is_int(value: object) -> bool:
    return type(value) is int


def _valid_ref(value: object, inputs: int, outputs: int) -> bool:
    if value in ("root", "entry"):
        return True
    if type(value) is not str:
        return False
    match = re.fullmatch(r"(input|output):([1-9][0-9]*)", value)
    if match is None:
        return False
    return int(match.group(2)) <= (inputs if match.group(1) == "input" else outputs)


def _validate_result(row: object, rule_id: str, inputs: int, outputs: int) -> None:
    _require(type(row) is dict and set(row) == RESULT_FIELDS)
    _require(row["rule_id"] == rule_id)
    status = row["status"]
    severity = row["severity"]
    complete = row["coverage_complete"]
    _require(type(status) is str and status in ("pass", "finding", "unknown"))
    _require(type(severity) is str and severity in ("none", "warning", "critical"))
    _require(type(complete) is bool)
    reason = row["reason_code"]
    refs = row["unknown_refs"]
    evidence = row["evidence"]
    _require(type(refs) is list and len(refs) <= 64)
    _require(all(_valid_ref(ref, inputs, outputs) for ref in refs))
    _require(type(evidence) is list and len(evidence) <= 64)
    if complete:
        _require(reason is None and not refs)
    else:
        _require(type(reason) is str and
                 reason in UNKNOWN_CODES[rule_id] | {"M1_RULE_PENDING"} and bool(refs))
    if status == "pass":
        _require(complete and severity == "none")
        allowed_codes = PASS_CODES[rule_id]
    elif status == "unknown":
        _require(not complete and severity == "none" and not evidence)
        allowed_codes = set()
    else:
        _require(severity in ("warning", "critical") and bool(evidence))
        allowed_codes = FINDING_CODES[rule_id]
    for item in evidence:
        _require(type(item) is dict and set(item) == {"code", "refs"})
        _require(type(item["code"]) is str and item["code"] in allowed_codes)
        item_refs = item["refs"]
        _require(type(item_refs) is list and len(item_refs) <= 2)
        _require(all(_valid_ref(ref, inputs, outputs) for ref in item_refs))
    if status == "finding":
        expected = "critical" if any(item["code"] in CRITICAL_CODES for item in evidence) else "warning"
        _require(severity == expected)


def aggregate_results(results: list[dict]) -> dict:
    """Compute counts and priority from rule results."""
    findings = sum(row["status"] == "finding" for row in results)
    unknowns = sum(not row["coverage_complete"] for row in results)
    if any(row["status"] == "finding" and row["severity"] == "critical"
           for row in results):
        status = "blocked"
    elif unknowns:
        status = "incomplete"
    elif findings:
        status = "review"
    else:
        status = "clear"
    return {"status": status, "finding_count": findings, "unknown_count": unknowns}


def validate_report(report: object) -> None:
    """Reject malformed, inconsistent, or potentially path-bearing v1 reports."""
    _require(type(report) is dict and set(report) == {
        "schema_version", "tool_version", "scope", "overall", "results",
    })
    _require(report["schema_version"] == "1.0")
    version = report["tool_version"]
    _require(type(version) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
             is not None)
    scope = report["scope"]
    _require(type(scope) is dict and set(scope) == {
        "root_ref", "entry_ref", "input_count", "output_count", "git_status_scope",
        "untracked_files_scanned",
    })
    _require(scope["root_ref"] == "root" and scope["entry_ref"] == "entry")
    inputs, outputs = scope["input_count"], scope["output_count"]
    _require(_is_int(inputs) and 1 <= inputs <= 32 and _is_int(outputs) and 1 <= outputs <= 32)
    _require(scope["git_status_scope"] == "entry_only")
    _require(scope["untracked_files_scanned"] is False)
    rows = report["results"]
    _require(type(rows) is list and len(rows) == len(RULE_IDS))
    for expected_id, row in zip(RULE_IDS, rows):
        _validate_result(row, expected_id, inputs, outputs)
    overall = report["overall"]
    _require(type(overall) is dict and set(overall) == {
        "status", "finding_count", "unknown_count",
    })
    _require(type(overall["status"]) is str)
    _require(_is_int(overall["finding_count"]) and _is_int(overall["unknown_count"]))
    _require(overall == aggregate_results(rows))


def build_report(results: list[dict], *, input_count: int, output_count: int) -> dict:
    """Build and validate a v1 report from rule results."""
    _require(_is_int(input_count) and 1 <= input_count <= 32)
    _require(_is_int(output_count) and 1 <= output_count <= 32)
    _require(type(results) is list and len(results) == len(RULE_IDS))
    for expected_id, row in zip(RULE_IDS, results):
        _validate_result(row, expected_id, input_count, output_count)
    report = {
        "schema_version": "1.0", "tool_version": __version__,
        "scope": {
            "root_ref": "root", "entry_ref": "entry", "input_count": input_count,
            "output_count": output_count, "git_status_scope": "entry_only",
            "untracked_files_scanned": False,
        },
        "overall": aggregate_results(results), "results": results,
    }
    validate_report(report)
    return report


def exit_code(report: dict) -> int:
    """Return 0 clear, 1 complete finding, or 2 incomplete."""
    validate_report(report)
    if report["overall"]["unknown_count"]:
        return 2
    return 1 if report["overall"]["finding_count"] else 0
