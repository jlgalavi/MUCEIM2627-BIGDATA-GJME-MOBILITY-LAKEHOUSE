#!/usr/bin/env bash
# Reproducible Linux/WSL2 setup. Invoke with bash; no executable bit is required.
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() { printf 'Usage: bash scripts/setup.sh [--venv PATH] [--kernel NAME]\n'; }
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="$HOME/.venvs/mobility-lakehouse-py311"
kernel_name='mobility-lakehouse-py311'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv) [[ $# -ge 2 && -n "$2" ]] || die '--venv requires a path'; venv_path="$2"; shift 2 ;;
    --kernel) [[ $# -ge 2 && -n "$2" ]] || die '--kernel requires a name'; kernel_name="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
[[ "$(uname -s)" == Linux ]] || die 'Use Linux or an Ubuntu/WSL2 terminal.'
[[ "$kernel_name" =~ ^[A-Za-z0-9._-]+$ ]] || die 'Kernel names may contain letters, digits, dots, hyphens, and underscores.'
[[ "$venv_path" == /* ]] || venv_path="$PWD/$venv_path"

# Validate an existing destination before installing or synchronizing anything.
if [[ -e "$venv_path" || -L "$venv_path" ]]; then
  [[ -f "$venv_path/pyvenv.cfg" && -x "$venv_path/bin/python" ]] || die "Destination is not a working virtual environment: $venv_path"
  "$venv_path/bin/python" -c 'import platform,sys; sys.exit(0 if platform.system()=="Linux" and sys.version_info[:3]==(3,11,17) and sys.prefix!=sys.base_prefix else 1)' \
    || die "Existing environment must use Linux Python 3.11.17; choose another --venv path: $venv_path"
fi

uv_bin="$(command -v uv || true)"
if [[ -z "$uv_bin" || "$uv_bin" == /mnt/* ]]; then
  uv_bin="$HOME/.local/bin/uv"
fi
if [[ ! -x "$uv_bin" ]]; then
  command -v curl >/dev/null || die 'Install curl with your Linux distribution package manager first.'
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  uv_bin="$HOME/.local/bin/uv"
fi
"$uv_bin" --version
"$uv_bin" python install 3.11.17
if [[ ! -e "$venv_path" ]]; then
  "$uv_bin" venv --python 3.11.17 "$venv_path"
fi
"$uv_bin" pip sync --python "$venv_path/bin/python" "$repo_root/requirements-linux.lock.txt"
"$venv_path/bin/python" -m ipykernel install --user --name "$kernel_name" \
  --display-name 'Mobility Lakehouse — Python 3.11 (Linux)'
"$venv_path/bin/python" - <<'PY'
import duckdb
with duckdb.connect() as con:
    for name in ('ducklake', 'spatial', 'httpfs'):
        con.execute('INSTALL ' + name)
        con.execute('LOAD ' + name)
        print('Installed and loaded:', name, flush=True)
PY
printf '\nSetup complete. Activate with:\n  source %q/bin/activate\n' "$venv_path"
printf 'Core checks:\n  %q/bin/python %q/scripts/check_environment.py\n' "$venv_path" "$repo_root"
printf 'Full checks:\n  %q/bin/python %q/scripts/check_environment.py --with-data --with-notebook --kernel %q\n' "$venv_path" "$repo_root" "$kernel_name"
