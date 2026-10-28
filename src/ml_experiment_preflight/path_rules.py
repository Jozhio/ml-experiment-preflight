"""Read-only checks for explicitly supplied paths."""

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .report import CRITICAL_CODES


@dataclass(frozen=True)
class Probe:
    state: str  # present, absent, or unknown
    physical: Path | None = None
    kind: str | None = None
    reason: str | None = None


def _explicit_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _network_path(path: Path) -> bool:
    # UNC shares and POSIX double-slash roots have implementation-dependent
    # identity and availability. Do not certify their relationship as safe.
    return str(path).startswith("\\\\") if os.name == "nt" else str(path).startswith("//")


def _link_like(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def _missing_chain_reason(path: Path) -> str | None:
    """Distinguish an ordinary missing component from a broken link or I/O gap."""
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            return None
        except PermissionError:
            return "permission"
        except OSError:
            return "io"
        if _link_like(info):
            try:
                part.resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                return "symlink"
    return None


def _probe(path: Path) -> Probe:
    if _network_path(path):
        return Probe("unknown", reason="io")
    try:
        physical = path.resolve(strict=True)
    except FileNotFoundError:
        reason = _missing_chain_reason(path)
        return Probe("unknown", reason=reason) if reason else Probe("absent")
    except PermissionError:
        return Probe("unknown", reason="permission")
    except RuntimeError:
        return Probe("unknown", reason="symlink")
    except (OSError, ValueError):
        return Probe("unknown", reason="io")
    try:
        mode = physical.stat().st_mode
    except PermissionError:
        return Probe("unknown", reason="permission")
    except OSError:
        return Probe("unknown", reason="io")
    kind = "dir" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "other"
    return Probe("present", physical=physical, kind=kind)


def _probe_output(path: Path) -> Probe:
    target = _probe(path)
    if target.state != "absent":
        return target
    parent = _probe(path.parent)
    if parent.state == "present" and parent.kind == "dir":
        return Probe("absent", physical=parent.physical / path.name)
    if parent.state == "unknown":
        return Probe("unknown", reason=parent.reason)
    return Probe("unknown", reason="parent")


def _parts(path: Path) -> tuple[str, ...]:
    return tuple(os.path.normcase(piece) for piece in path.parts)


def _relation(left: Path, right: Path) -> str:
    """Compare resolved paths by components, never by string prefixes."""
    a, b = _parts(left), _parts(right)
    if not a or not b or a[0] != b[0]:
        return "unknown"
    if a == b:
        return "equal"
    if len(a) < len(b) and a == b[:len(a)]:
        return "ancestor"
    if len(b) < len(a) and b == a[:len(b)]:
        return "descendant"
    return "disjoint"


def _inside_or_equal(root: Path, target: Path) -> bool:
    a, b = _parts(root), _parts(target)
    return len(a) <= len(b) and a == b[:len(a)]


def _row(rule_id: str, evidence: list[dict], unknown_refs: list[str],
         reason: str | None) -> dict:
    if evidence:
        status = "finding"
        severity = ("critical" if any(item["code"] in CRITICAL_CODES for item in evidence)
                    else "warning")
    elif unknown_refs:
        status, severity = "unknown", "none"
    else:
        status, severity = "pass", "none"
    return {
        "rule_id": rule_id, "status": status, "severity": severity,
        "coverage_complete": not unknown_refs, "reason_code": reason if unknown_refs else None,
        "unknown_refs": unknown_refs, "evidence": evidence,
    }


def _path_reason(probe: Probe) -> str:
    return {"permission": "PERMISSION_DENIED", "symlink": "SYMLINK_UNRESOLVED"}.get(
        probe.reason, "PATH_IO_ERROR")


def _output_reason(probe: Probe) -> str:
    return {
        "permission": "PERMISSION_DENIED", "symlink": "SYMLINK_UNRESOLVED",
        "parent": "OUTPUT_PARENT_UNKNOWN",
    }.get(probe.reason, "PATH_IO_ERROR")


def evaluate_path_rules(root: Path, entry: str, inputs: list[tuple[str, str]],
                        outputs: list[tuple[str, str]]) -> tuple[dict, dict, dict]:
    """Return PATH-001, OUT-001 and OUT-002 using metadata only."""
    entry_probe = _probe(_explicit_path(root, entry))
    input_probes = [(_probe(_explicit_path(root, raw)), kind)
                    for kind, raw in inputs]
    output_probes = [(_probe_output(_explicit_path(root, raw)), kind)
                     for kind, raw in outputs]

    path_evidence: list[dict] = []
    path_unknown: list[str] = []
    path_reason: str | None = None
    for ref, probe, expected in [("entry", entry_probe, "file"), *(
            (f"input:{number}", probe, kind)
            for number, (probe, kind) in enumerate(input_probes, 1))]:
        if probe.state == "unknown":
            path_unknown.append(ref)
            path_reason = path_reason or _path_reason(probe)
        elif probe.state == "absent":
            path_evidence.append({"code": "ENTRY_MISSING" if ref == "entry" else "INPUT_MISSING",
                                  "refs": [ref]})
        else:
            if probe.kind != expected:
                path_evidence.append({"code": "TYPE_MISMATCH", "refs": [ref]})
            if ref == "entry" and not _inside_or_equal(root, probe.physical):
                path_evidence.append({"code": "ENTRY_ESCAPES_ROOT", "refs": [ref]})

    output_evidence: list[dict] = []
    output_unknown: list[str] = []
    output_reason: str | None = None
    for number, (probe, expected) in enumerate(output_probes, 1):
        ref = f"output:{number}"
        if probe.state == "unknown":
            output_unknown.append(ref)
            output_reason = output_reason or _output_reason(probe)
        elif probe.state == "present":
            code = "OUTPUT_EXISTS" if probe.kind == expected else "OUTPUT_TYPE_MISMATCH"
            output_evidence.append({"code": code, "refs": [ref]})

    overlap_evidence: list[dict] = []
    overlap_unknown: list[str] = []
    overlap_reason: str | None = None

    def unknown(ref: str, reason: str = "PATH_COMPARISON_UNKNOWN") -> None:
        nonlocal overlap_reason
        if ref not in overlap_unknown:
            if len(overlap_unknown) < 64:
                overlap_unknown.append(ref)
            else:
                overlap_reason = "EVIDENCE_LIMIT"
        overlap_reason = overlap_reason or reason

    def finding(code: str, left: str, right: str) -> None:
        nonlocal overlap_reason
        if len(overlap_evidence) < 64:
            overlap_evidence.append({"code": code, "refs": [left, right]})
        else:
            unknown(left, "EVIDENCE_LIMIT")
            overlap_reason = "EVIDENCE_LIMIT"

    for number, (output_probe, declared_kind) in enumerate(output_probes, 1):
        output_ref = f"output:{number}"
        if output_probe.state == "unknown":
            reason = ("OUTPUT_PARENT_UNKNOWN" if output_probe.reason == "parent" else
                      "SYMLINK_UNRESOLVED" if output_probe.reason == "symlink" else
                      "PATH_COMPARISON_UNKNOWN")
            unknown(output_ref, reason)
            continue
        output_path = output_probe.physical
        output_is_dir = (output_probe.kind == "dir" if output_probe.state == "present"
                         else declared_kind == "dir")

        root_relation = _relation(output_path, root)
        if root_relation == "unknown":
            unknown(output_ref)
        elif output_is_dir and root_relation in ("equal", "ancestor"):
            finding("OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT", output_ref, "root")

        for ref, target_probe, target_kind in [("entry", entry_probe, "file"), *(
                (f"input:{index}", probe, kind)
                for index, (probe, kind) in enumerate(input_probes, 1))]:
            if target_probe.state != "present":
                unknown(ref)
                continue
            relation = _relation(output_path, target_probe.physical)
            if (relation == "disjoint" and output_probe.state == "present" and
                    output_probe.kind == target_probe.kind):
                try:
                    if output_path.samefile(target_probe.physical):
                        relation = "equal"
                except (OSError, ValueError, RuntimeError):
                    unknown(output_ref)
                    continue
            if relation == "unknown":
                unknown(output_ref)
            elif relation == "equal":
                finding("OUTPUT_EQUALS_INPUT_OR_ENTRY", output_ref, ref)
            elif output_is_dir and relation == "ancestor":
                finding("OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT", output_ref, ref)
            elif target_kind == "dir" and relation == "descendant":
                finding("OUTPUT_INSIDE_INPUT_DIR", output_ref, ref)

    return (
        _row("PATH-001", path_evidence, path_unknown, path_reason),
        _row("OUT-001", output_evidence, output_unknown, output_reason),
        _row("OUT-002", overlap_evidence, overlap_unknown, overlap_reason),
    )
