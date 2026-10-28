$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ml-preflight-normal-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    Copy-Item -Path (Join-Path $PSScriptRoot "fixture\*") -Destination $Tmp -Recurse -Force
    New-Item -ItemType Directory -Path (Join-Path $Tmp "runs") -Force | Out-Null
    git -C $Tmp init -q
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    git -C $Tmp add train.py
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }
    git -C $Tmp -c user.name=Synthetic -c user.email=synthetic@example.invalid commit -qm init
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

    $env:PYTHONPATH = (Join-Path $RepoRoot "src")
    if (Get-Command ml-experiment-preflight -ErrorAction SilentlyContinue) {
        ml-experiment-preflight check --root $Tmp --entry train.py --input-file data/input.bin --output-file runs/model.bin --format json
    } else {
        python -m ml_experiment_preflight check --root $Tmp --entry train.py --input-file data/input.bin --output-file runs/model.bin --format json
    }
    $code = $LASTEXITCODE
    Write-Host ""
    Write-Host "Expected exit code: 0; actual: $code"
    exit $code
} finally {
    Remove-Item -Path $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}
