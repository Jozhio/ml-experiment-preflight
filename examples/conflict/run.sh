#!/usr/bin/env bash
set -eu

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/ml-preflight-conflict.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

cp -R "$script_dir/fixture/." "$tmp/"
git -C "$tmp" init -q
git -C "$tmp" add train.py
git -C "$tmp" -c user.name=Synthetic -c user.email=synthetic@example.invalid commit -qm init

python_bin="${PYTHON:-}"
if [ -z "$python_bin" ]; then
    if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
        python_bin=python3
    elif command -v python >/dev/null 2>&1 && python -c "import sys" >/dev/null 2>&1; then
        python_bin=python
    else
        echo "ERROR: Python 3.11+ is required" >&2
        exit 2
    fi
fi

export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"
set +e
if command -v ml-experiment-preflight >/dev/null 2>&1; then
    ml-experiment-preflight check --root "$tmp" --entry train.py --input-file data/input.bin --output-file data/input.bin --format json
else
    "$python_bin" -m ml_experiment_preflight check --root "$tmp" --entry train.py --input-file data/input.bin --output-file data/input.bin --format json
fi
code=$?
set -e
echo ""
echo "Expected exit code: 1; actual: $code"
exit "$code"
