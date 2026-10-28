"""Read-only Git adapter and GIT-001/002/003 rules."""

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
import time


GIT_TIMEOUT_SECONDS = 5
GIT_MAX_OUTPUT_BYTES = 1024 * 1024

# Global options are fixed and precede every subcommand.  They avoid optional
# index locks, lazy network fetches, pathspec expansion and a pager.
_GIT_GLOBAL_OPTIONS = (
    "--no-optional-locks",
    "--no-lazy-fetch",
    "--literal-pathspecs",
    "--no-pager",
)

# Repository-local configuration is still readable by Git.  These command-line
# overrides neutralise the options that could otherwise hide changes or spawn
# external helpers during status.
_GIT_CONFIG_OVERRIDES = (
    "-c", "core.fsmonitor=false",
    "-c", "core.ignoreStat=false",
    "-c", "core.untrackedCache=false",
)

_UNAVAILABLE_ENTRY_CODES = {
    "ENTRY_MISSING",
    "TYPE_MISMATCH",
    "ENTRY_ESCAPES_ROOT",
}


@dataclass(frozen=True)
class GitRun:
    returncode: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    failure: str | None = None


@dataclass(frozen=True)
class RepoCheck:
    state: str
    reason: str | None = None


def _link_like(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def _git_env() -> dict[str, str]:
    """Return a minimal Git environment without inherited Git redirects."""
    env = os.environ.copy()
    for key in tuple(env):
        if key.upper().startswith("GIT_"):
            env.pop(key, None)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "GCM_INTERACTIVE": "never",
        "LC_ALL": "C",
        "LANG": "C",
    })
    return env


def _find_git_executable(root: Path) -> str | None:
    """Find Git in absolute PATH directories, never via cwd or project files."""
    cwd = Path.cwd().resolve()
    name = "git.exe" if os.name == "nt" else "git"
    for raw_directory in os.get_exec_path():
        directory = Path(raw_directory)
        if not directory.is_absolute() or str(directory).startswith(("\\\\", "//")):
            continue
        candidate = directory / name
        if (candidate.is_relative_to(root) or candidate.is_relative_to(cwd)):
            continue
        try:
            physical = candidate.resolve(strict=True)
            if (physical.is_relative_to(root) or physical.is_relative_to(cwd)
                    or not physical.is_file() or not os.access(physical, os.X_OK)):
                continue
        except (OSError, ValueError, RuntimeError):
            continue
        return str(physical)
    return None


class _BoundedCapture:
    """Retain at most a fixed number of combined stdout/stderr bytes."""

    def __init__(self, limit: int):
        self.limit = limit
        self.total = 0
        self.overflow = threading.Event()
        self.lock = threading.Lock()
        self.parts = {"stdout": bytearray(), "stderr": bytearray()}

    def add(self, name: str, chunk: bytes) -> None:
        with self.lock:
            if self.overflow.is_set():
                return
            remaining = self.limit - self.total
            if len(chunk) > remaining:
                if remaining > 0:
                    self.parts[name].extend(chunk[:remaining])
                self.total = self.limit
                self.overflow.set()
            else:
                self.parts[name].extend(chunk)
                self.total += len(chunk)

    def bytes(self, name: str) -> bytes:
        return bytes(self.parts[name])


def _drain(pipe, name: str, capture: _BoundedCapture) -> None:
    try:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            capture.add(name, chunk)
            if capture.overflow.is_set():
                break
    except (OSError, ValueError):
        pass
    finally:
        try:
            pipe.close()
        except (OSError, ValueError):
            pass


def _kill_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def _run_process(command: list[str], *, timeout: float, max_output: int,
                 env: dict[str, str]) -> GitRun:
    """Run a local process while bounding combined stdout/stderr retention."""
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=env,
            start_new_session=(os.name != "nt"),
            creationflags=creationflags,
        )
    except (OSError, ValueError):
        return GitRun(None, failure="unavailable")

    capture = _BoundedCapture(max_output)
    stdout_thread = threading.Thread(
        target=_drain, args=(process.stdout, "stdout", capture), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_drain, args=(process.stderr, "stderr", capture), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    started = time.monotonic()
    timed_out = False
    while True:
        if capture.overflow.is_set():
            _kill_process(process)
            break
        if process.poll() is not None:
            break
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            timed_out = True
            _kill_process(process)
            break
        try:
            process.wait(timeout=min(0.05, remaining))
            break
        except subprocess.TimeoutExpired:
            continue

    if process.poll() is None:
        _kill_process(process)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill_process(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        for pipe in (process.stdout, process.stderr):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    if capture.overflow.is_set():
        return GitRun(process.returncode, failure="output_limit")
    if timed_out:
        return GitRun(process.returncode, failure="timeout")
    if process.returncode is None:
        return GitRun(None, failure="error")
    return GitRun(process.returncode, capture.bytes("stdout"), capture.bytes("stderr"))


def _run_git(root: Path, args: list[str], git_exe: str | None) -> GitRun:
    if not git_exe:
        return GitRun(None, failure="unavailable")
    command = [
        git_exe,
        *_GIT_GLOBAL_OPTIONS,
        "-C", str(root),
        *_GIT_CONFIG_OVERRIDES,
        *args,
    ]
    return _run_process(
        command,
        timeout=GIT_TIMEOUT_SECONDS,
        max_output=GIT_MAX_OUTPUT_BYTES,
        env=_git_env(),
    )


def _stderr_error(run: GitRun) -> bool:
    text = run.stderr.lower()
    return b"error:" in text or b"fatal:" in text


def _ok(run: GitRun) -> bool:
    return run.failure is None and run.returncode == 0 and not _stderr_error(run)


def _single_path(run: GitRun) -> str | None:
    if not _ok(run):
        return None
    raw = run.stdout.rstrip(b"\r\n")
    if not raw or b"\n" in raw or b"\r" in raw:
        return None
    return os.fsdecode(raw)


def _z_chunks(data: bytes):
    for chunk in data.split(b"\0"):
        if chunk:
            yield chunk


def _path_key(value: str) -> str:
    if os.name == "nt":
        value = value.replace("\\", "/")
    return os.path.normcase(value)


def _tracked(stdout: bytes, pathspec: str) -> bool:
    wanted = _path_key(pathspec)
    return any(_path_key(os.fsdecode(chunk)) == wanted for chunk in _z_chunks(stdout))


def _entry_tags(stdout: bytes, pathspec: str) -> list[str]:
    wanted = _path_key(pathspec)
    tags: list[str] = []
    for chunk in _z_chunks(stdout):
        if len(chunk) < 3 or chunk[1:2] != b" ":
            continue
        if _path_key(os.fsdecode(chunk[2:])) == wanted:
            tags.append(chunk[:1].decode("ascii", "replace"))
    return tags


def _entry_pathspec(root: Path, entry: str) -> str | None:
    path = Path(entry)
    try:
        if path.is_absolute():
            relative = os.path.relpath(str(path), str(root))
            # Windows may spell the same root with an 8.3 component in one
            # path and its long name in the other. Preserve the entry name,
            # but compare resolved parents when the lexical path escapes.
            if relative == os.pardir or relative.startswith(os.pardir + os.sep):
                relative = os.path.relpath(
                    str(path.parent.resolve(strict=True) / path.name),
                    str(root.resolve(strict=True)),
                )
        else:
            relative = os.path.normpath(entry)
    except (OSError, ValueError, RuntimeError):
        return None
    if (not relative
            or relative in (os.curdir, os.pardir)
            or os.path.isabs(relative)
            or relative.startswith(os.pardir + os.sep)):
        return None
    return Path(relative).as_posix()


def _entry_unavailable(path_row: dict) -> bool:
    if path_row.get("status") == "unknown" and "entry" in path_row.get("unknown_refs", []):
        return True
    for evidence in path_row.get("evidence", []):
        if (evidence.get("code") in _UNAVAILABLE_ENTRY_CODES
                and "entry" in evidence.get("refs", [])):
            return True
    return False


def _result(rule_id: str, status: str, severity: str, coverage_complete: bool,
            reason_code: str | None, unknown_refs: list[str],
            evidence: list[dict]) -> dict:
    return {
        "rule_id": rule_id,
        "status": status,
        "severity": severity,
        "coverage_complete": coverage_complete,
        "reason_code": reason_code,
        "unknown_refs": unknown_refs,
        "evidence": evidence,
    }


def _pass(rule_id: str, code: str, ref: str) -> dict:
    return _result(rule_id, "pass", "none", True, None, [],
                   [{"code": code, "refs": [ref]}])


def _finding(rule_id: str, code: str, ref: str) -> dict:
    return _result(rule_id, "finding", "warning", True, None, [],
                   [{"code": code, "refs": [ref]}])


def _unknown(rule_id: str, reason: str, ref: str) -> dict:
    return _result(rule_id, "unknown", "none", False, reason, [ref], [])


def _repo_failure_reason(failure: str | None) -> str:
    if failure == "unavailable":
        return "GIT_UNAVAILABLE"
    if failure == "timeout":
        return "GIT_TIMEOUT"
    return "GIT_ERROR"


def _command_reason(run: GitRun, *, allow_output_limit: bool) -> str:
    if run.failure == "timeout":
        return "GIT_TIMEOUT"
    if run.failure == "output_limit" and allow_output_limit:
        return "GIT_OUTPUT_LIMIT"
    return "GIT_ERROR"


def _check_repository(root: Path, git_exe: str | None) -> RepoCheck:
    try:
        info = (root / ".git").lstat()
    except FileNotFoundError:
        return RepoCheck("no_repo")
    except OSError:
        return RepoCheck("error", "GIT_ERROR")
    if _link_like(info) or not stat.S_ISDIR(info.st_mode):
        return RepoCheck("unsupported", "UNSUPPORTED_GIT_LAYOUT")
    if not git_exe:
        return RepoCheck("error", "GIT_UNAVAILABLE")

    top_run = _run_git(root, ["rev-parse", "--show-toplevel"], git_exe)
    if top_run.failure:
        return RepoCheck("error", _repo_failure_reason(top_run.failure))
    top = _single_path(top_run)
    if top is None:
        return RepoCheck("error", "GIT_ERROR")
    try:
        same_root = Path(top).samefile(root)
    except (OSError, ValueError, RuntimeError):
        return RepoCheck("error", "GIT_ERROR")
    if not same_root:
        return RepoCheck("root_mismatch", "GIT_ROOT_MISMATCH")

    head_run = _run_git(root, ["rev-parse", "--verify", "--quiet", "HEAD"], git_exe)
    if head_run.failure:
        return RepoCheck("error", _repo_failure_reason(head_run.failure))
    if _stderr_error(head_run):
        return RepoCheck("error", "GIT_ERROR")
    if head_run.returncode == 0:
        return RepoCheck("ok")
    if head_run.returncode == 1:
        return RepoCheck("no_head", "NO_HEAD")
    return RepoCheck("error", "GIT_ERROR")


def _context_unknown() -> tuple[dict, dict]:
    return (
        _unknown("GIT-002", "GIT_CONTEXT_UNKNOWN", "entry"),
        _unknown("GIT-003", "GIT_CONTEXT_UNKNOWN", "entry"),
    )


def evaluate_git_rules(root: Path, entry: str, path_row: dict) -> tuple[dict, dict, dict]:
    """Return GIT-001, GIT-002 and GIT-003 using local metadata only."""
    git_exe = _find_git_executable(root)
    repo = _check_repository(root, git_exe)

    if repo.state == "no_repo":
        return (_finding("GIT-001", "NO_REPOSITORY", "root"), *_context_unknown())
    if repo.state == "no_head":
        return (_finding("GIT-001", "NO_HEAD", "root"), *_context_unknown())
    if repo.state == "unsupported":
        return (_unknown("GIT-001", repo.reason or "UNSUPPORTED_GIT_LAYOUT", "root"),
                *_context_unknown())
    if repo.state == "root_mismatch":
        return (_unknown("GIT-001", repo.reason or "GIT_ROOT_MISMATCH", "root"),
                *_context_unknown())
    if repo.state == "error":
        return (_unknown("GIT-001", repo.reason or "GIT_ERROR", "root"),
                *_context_unknown())

    git001 = _pass("GIT-001", "REPOSITORY_WITH_HEAD", "root")
    if _entry_unavailable(path_row):
        return (git001,
                _unknown("GIT-002", "ENTRY_UNAVAILABLE", "entry"),
                _unknown("GIT-003", "ENTRY_UNAVAILABLE", "entry"))

    pathspec = _entry_pathspec(root, entry)
    if pathspec is None:
        return (git001,
                _unknown("GIT-002", "ENTRY_UNAVAILABLE", "entry"),
                _unknown("GIT-003", "ENTRY_UNAVAILABLE", "entry"))

    tracked_run = _run_git(root, ["ls-files", "--cached", "-z", "--", pathspec], git_exe)
    if not _ok(tracked_run):
        return (git001,
                _unknown("GIT-002", _command_reason(tracked_run, allow_output_limit=True),
                         "entry"),
                _unknown("GIT-003", _command_reason(tracked_run, allow_output_limit=False),
                         "entry"))

    if not _tracked(tracked_run.stdout, pathspec):
        return (git001,
                _unknown("GIT-002", "ENTRY_NOT_TRACKED", "entry"),
                _finding("GIT-003", "ENTRY_NOT_TRACKED", "entry"))

    git003 = _pass("GIT-003", "ENTRY_TRACKED", "entry")

    flags_run = _run_git(root, ["ls-files", "-v", "-z", "--", pathspec], git_exe)
    if not _ok(flags_run):
        return (git001,
                _unknown("GIT-002", _command_reason(flags_run, allow_output_limit=True),
                         "entry"),
                git003)

    tags = _entry_tags(flags_run.stdout, pathspec)
    if not tags:
        return (git001, _unknown("GIT-002", "GIT_ERROR", "entry"), git003)
    if any(tag != "H" for tag in tags):
        if all(tag == "S" or tag.islower() for tag in tags):
            reason = "GIT_ENTRY_FLAG_UNSUPPORTED"
        else:
            reason = "GIT_ERROR"
        return (git001, _unknown("GIT-002", reason, "entry"), git003)

    status_run = _run_git(
        root,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=no",
            "--ignore-submodules=all",
            "--no-renames",
            "--",
            pathspec,
        ],
        git_exe,
    )
    if not _ok(status_run):
        return (git001,
                _unknown("GIT-002", _command_reason(status_run, allow_output_limit=True),
                         "entry"),
                git003)

    if status_run.stdout:
        git002 = _finding("GIT-002", "ENTRY_CHANGED", "entry")
    else:
        git002 = _pass("GIT-002", "ENTRY_UNCHANGED", "entry")
    return (git001, git002, git003)
