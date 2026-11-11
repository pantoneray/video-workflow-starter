#!/bin/sh
set -eu
cd "$(dirname "$0")"
mode="${1:-base}"
case "$mode" in base|corpus-pdf|packaging|align|heygen|heygen-api|youtube|all) ;; *) echo '用法: ./install.sh [base|corpus-pdf|packaging|align|heygen|heygen-api|youtube|all]' >&2; exit 2;; esac
sh ./check-env
python_bin="${PYTHON_BIN:-python3}"
venv_dir=.venv
case "$(uname -r)" in *microsoft*|*Microsoft*) venv_dir=.venv-wsl;; esac
"$python_bin" -m venv "$venv_dir"
if [ "$mode" = heygen-api ] || [ "$mode" = all ]; then
  "$venv_dir/bin/python" -m pip install -r requirements-heygen.txt
fi
if [ "$mode" = packaging ] || [ "$mode" = all ]; then
  "$venv_dir/bin/python" -m pip install -r requirements-packaging.txt
  "$venv_dir/bin/python" scripts/check_env.py --with-captions
fi
if [ "$mode" = corpus-pdf ] || [ "$mode" = all ]; then
  "$venv_dir/bin/python" -m pip install -r requirements-corpus-pdf.txt
fi
if [ "$mode" = align ] || [ "$mode" = all ]; then
  align_venv=.venv-align
  case "$(uname -r)" in *microsoft*|*Microsoft*) align_venv=.venv-align-wsl;; esac
  "$python_bin" -m venv "$align_venv"
  "$align_venv/bin/python" -m pip install -r tools/faithful-audio-align/requirements.txt
fi
if [ "$mode" = heygen ] || [ "$mode" = all ]; then
  if [ ! -x .tools/bin/heygen ]; then
    installer="$(mktemp)"
    curl --fail --location --silent --show-error --max-time 30 https://static.heygen.ai/cli/install.sh -o "$installer"
    INSTALL_DIR="$PWD/.tools/bin" bash "$installer" --version "${HEYGEN_CLI_VERSION:-v0.11.0}"
    rm -f "$installer"
  fi
  sh ./check-env --with-heygen-cli
fi
if [ "$mode" = youtube ] || [ "$mode" = all ]; then
  "$venv_dir/bin/python" -m pip install -r requirements-youtube.txt
fi
echo "安装完成：$mode"
if [ "$mode" = heygen ] || [ "$mode" = all ]; then
  echo '网页 Review & Edit 路线使用 HeyGen CLI OAuth。'
  echo '请在交互终端运行：./.tools/bin/heygen auth login --oauth'
  echo '随后运行：python3 scripts/heygen_web.py auth-check --expected-email "你的HeyGen账号邮箱"'
  echo '先确认登录的是正确账号，再创建草稿；HEYGEN_API_KEY 环境变量会覆盖 CLI OAuth，须先取消。'
fi
