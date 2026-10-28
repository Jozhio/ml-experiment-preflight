"""Bounded CLI parsing and redacted rendering for the preflight report."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

from .git_rules import evaluate_git_rules
from .path_rules import evaluate_path_rules
from .report import build_report, exit_code, validate_report


class UsageError(Exception):
    """Invalid command input; its message is intentionally never printed."""


USAGE_HELP = (
    "usage: ml-experiment-preflight check --root ROOT --entry ENTRY "
    "(--input-file PATH | --input-dir PATH) "
    "(--output-file PATH | --output-dir PATH) [--format json|text]"
)


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError from None


class AppendTypedPath(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        current = getattr(namespace, self.dest, None)
        if current is None:
            current = []
        current.append(("file" if option_string.endswith("-file") else "dir", values))
        setattr(namespace, self.dest, current)


class StoreOnce(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            raise UsageError
        setattr(namespace, self.dest, values)


def _parser() -> SafeParser:
    parser = SafeParser(prog="ml-experiment-preflight")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=SafeParser)
    check = sub.add_parser("check")
    check.add_argument("--root", required=True, action=StoreOnce)
    check.add_argument("--entry", required=True, action=StoreOnce)
    check.add_argument("--input-file", dest="inputs", action=AppendTypedPath)
    check.add_argument("--input-dir", dest="inputs", action=AppendTypedPath)
    check.add_argument("--output-file", dest="outputs", action=AppendTypedPath)
    check.add_argument("--output-dir", dest="outputs", action=AppendTypedPath)
    check.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def _lexical_path(root: Path, raw: str) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return os.path.normcase(os.path.normpath(str(path)))


def _ambiguous_anchor(raw: str) -> bool:
    path = Path(raw)
    return bool(path.anchor and not path.is_absolute())


def _short_alias_parent(root: Path, entry_path: Path) -> bool:
    return (os.name == "nt" and entry_path.is_absolute()
            and entry_path.drive.casefold() == root.drive.casefold()
            and not entry_path.drive.startswith("\\\\")
            and any(re.search(r"~[0-9]+(?:\.|$)", piece)
                    for piece in entry_path.parent.parts))


def _validate(args) -> tuple[Path, int, int]:
    if any(not value or "\x00" in value or "*" in value or "?" in value or
           value.startswith("@") or _ambiguous_anchor(value)
           for value in (args.root, args.entry)):
        raise UsageError
    root_path = Path(args.root)
    if (str(root_path).startswith("//") or
            (os.name == "nt" and root_path.drive.startswith("\\\\"))):
        raise UsageError
    try:
        root = root_path.resolve(strict=True)
        root_is_dir = root.is_dir()
    except (OSError, ValueError, RuntimeError) as error:
        raise UsageError from error
    if not root_is_dir:
        raise UsageError
    inputs = args.inputs or []
    outputs = args.outputs or []
    if not 1 <= len(inputs) <= 32 or not 1 <= len(outputs) <= 32:
        raise UsageError
    entry = _lexical_path(root, args.entry)
    root_lexical = os.path.normcase(os.path.normpath(str(root)))
    try:
        entry_inside_root = os.path.commonpath((root_lexical, entry)) == root_lexical
    except ValueError as error:
        raise UsageError from error
    entry_path = Path(args.entry)
    if not entry_inside_root and _short_alias_parent(root, entry_path):
        # A Windows 8.3 spelling can be lexically different from the long
        # spelling returned by root.resolve(). Resolve only the existing parent
        # of this narrow local alias; PATH-001 checks the final entry itself.
        try:
            physical_entry = os.path.normcase(
                os.path.normpath(str(entry_path.parent.resolve(strict=True) / entry_path.name))
            )
            entry_inside_root = (
                os.path.commonpath((root_lexical, physical_entry)) == root_lexical
            )
        except (OSError, ValueError, RuntimeError) as error:
            raise UsageError from error
    if not entry_inside_root:
        raise UsageError
    for group in (inputs, outputs):
        seen = set()
        for kind, raw in group:
            if (not raw or "\x00" in raw or "*" in raw or "?" in raw or
                    raw.startswith("@") or _ambiguous_anchor(raw)):
                raise UsageError
            key = _lexical_path(root, raw)
            if key in seen:
                raise UsageError
            seen.add(key)
    return root, len(inputs), len(outputs)


def run_check(argv=None) -> tuple[dict, str]:
    """Build a checked report; programming errors propagate to direct callers."""
    args = _parser().parse_args(argv)
    root, input_count, output_count = _validate(args)
    path_rows = evaluate_path_rules(root, args.entry, args.inputs, args.outputs)
    git_rows = evaluate_git_rules(root, args.entry, path_rows[0])
    report = build_report([*git_rows, *path_rows],
                          input_count=input_count, output_count=output_count)
    validate_report(report)
    return report, args.format


def main(argv=None) -> int:
    try:
        report, output_format = run_check(argv)
        if output_format == "json":
            print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"ml-experiment-preflight: {report['overall']['status']}")
            for result in report["results"]:
                detail = result["reason_code"] or result["severity"]
                print(f"{result['rule_id']}: {result['status']} ({detail})")
        return exit_code(report)
    except UsageError:
        print("USAGE_ERROR", file=sys.stderr)
        print(USAGE_HELP, file=sys.stderr)
        return 2
    except Exception:
        # The public CLI stays redacted. run_check retains the original exception
        # for tests and trusted callers, so internal faults cannot become pass.
        print("REPORT_ERROR", file=sys.stderr)
        return 2
