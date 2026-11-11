$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path .\.venv\Scripts\python.exe) {
    & .\.venv\Scripts\python.exe scripts/check_env.py @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 scripts/check_env.py @args
} else {
    & python scripts/check_env.py @args
}
exit $LASTEXITCODE
