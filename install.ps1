param([ValidateSet('base','corpus-pdf','packaging','align','heygen','heygen-api','youtube','all')][string]$Mode = 'base')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\check-env.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
else { & python -m venv .venv }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Mode -eq 'heygen-api' -or $Mode -eq 'all') {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-heygen.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Mode -eq 'packaging' -or $Mode -eq 'all') {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-packaging.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .\.venv\Scripts\python.exe scripts/check_env.py --with-captions
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Mode -eq 'corpus-pdf' -or $Mode -eq 'all') {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-corpus-pdf.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Mode -eq 'align' -or $Mode -eq 'all') {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 --version *> $null
        if ($LASTEXITCODE -eq 0) { & py -3.11 -m venv .venv-align }
        else {
            & py -3.12 --version *> $null
            if ($LASTEXITCODE -eq 0) { & py -3.12 -m venv .venv-align }
            else { throw '强制对齐请先安装 Python 3.11 或 3.12' }
        }
    } else { & python -m venv .venv-align }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .\.venv-align\Scripts\python.exe -m pip install -r tools\faithful-audio-align\requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Mode -eq 'youtube' -or $Mode -eq 'all') {
    & .\.venv\Scripts\python.exe -m pip install -r requirements-youtube.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Output "安装完成：$Mode"
if ($Mode -eq 'heygen' -or $Mode -eq 'all') {
    Write-Output 'HeyGen 网页 Review & Edit 使用官方 CLI OAuth；官方 CLI 在 Windows 通过 WSL 运行。'
    Write-Output '在 WSL 终端进入本包目录，运行 bash ./install.sh heygen，再运行 ./.tools/bin/heygen auth login --oauth。'
    Write-Output '登录后用 python3 scripts/heygen_web.py auth-check --expected-email "你的HeyGen账号邮箱" 核对账号。'
}
