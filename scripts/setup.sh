#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="${VENV_PATH:-$repo_root/.venv}"
[[ "$(uname -s)" == Linux ]] || { echo 'Run in Ubuntu or WSL2.' >&2; exit 1; }
if [[ $# -gt 0 ]]; then
  [[ $# == 2 && "$1" == --venv ]] || { echo 'Usage: bash scripts/setup.sh [--venv PATH]' >&2; exit 1; }
  venv_path="$2"
fi
uv_bin="$(command -v uv || true)"
if [[ -z "$uv_bin" || "$uv_bin" == /mnt/* ]]; then uv_bin="$HOME/.local/bin/uv"; fi
if [[ ! -x "$uv_bin" ]]; then
  command -v curl >/dev/null || { echo 'Install curl first.' >&2; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  uv_bin="$HOME/.local/bin/uv"
fi
"$uv_bin" python install 3.11.17
if [[ -e "$venv_path" ]]; then
  [[ -f "$venv_path/pyvenv.cfg" && -x "$venv_path/bin/python" ]] || { echo 'Destination is not a Linux venv.' >&2; exit 1; }
  "$venv_path/bin/python" -c 'import sys; assert sys.version_info[:3] == (3,11,17), "Choose a new --venv path for Python 3.11.17"'
else
  "$uv_bin" venv --python 3.11.17 "$venv_path"
fi
"$uv_bin" pip sync --python "$venv_path/bin/python" "$repo_root/requirements-linux.lock.txt"
"$venv_path/bin/python" - <<'PY'
import duckdb
with duckdb.connect() as con:
    for name in ('ducklake', 'spatial'):
        con.execute('INSTALL ' + name)
        con.execute('LOAD ' + name)
        print('Ready:', name)
PY
printf 'Activate: source %q/bin/activate\n' "$venv_path"
