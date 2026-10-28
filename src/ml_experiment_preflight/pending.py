"""Explicit placeholders retained for rules not yet implemented."""

from .report import RULE_IDS, build_report


def pending_results(input_count: int, output_count: int) -> list[dict]:
    input_refs = [f"input:{n}" for n in range(1, input_count + 1)]
    output_refs = [f"output:{n}" for n in range(1, output_count + 1)]
    rows = []
    for rule_id in RULE_IDS:
        if rule_id == "GIT-001":
            refs = ["root"]
        elif rule_id.startswith("GIT-"):
            refs = ["entry"]
        elif rule_id == "PATH-001":
            refs = ["entry", *input_refs]
        elif rule_id == "OUT-001":
            refs = output_refs
        else:
            refs = ["root", "entry", *input_refs, *output_refs][:64]
        rows.append({
            "rule_id": rule_id, "status": "unknown", "severity": "none",
            "coverage_complete": False, "reason_code": "M1_RULE_PENDING",
            "unknown_refs": refs, "evidence": [],
        })
    return rows


def pending_report(input_count: int, output_count: int) -> dict:
    return build_report(pending_results(input_count, output_count),
                        input_count=input_count, output_count=output_count)
