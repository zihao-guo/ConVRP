#!/usr/bin/env bash
set -eo pipefail

GUROBI_LICENSE="/mnt/c/Users/User/Downloads/gurobi.lic"
PYTHON_VERSION="3.11"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"

fail_activate_env() {
  echo "$1" >&2
  if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return 1
  fi
  exit 1
}

detect_conda_root() {
  if [[ -n "${CONDA_ROOT:-}" ]]; then
    echo "$CONDA_ROOT"
    return 0
  fi
  if [[ -n "${CONDA_EXE:-}" ]]; then
    cd "$(dirname "$CONDA_EXE")/.." && pwd
    return 0
  fi
  for candidate in "$HOME/miniconda3" "$HOME/anaconda3" "/opt/conda"; do
    if [[ -f "$candidate/etc/profile.d/conda.sh" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

CONDA_ROOT="$(detect_conda_root)" || fail_activate_env "Missing conda installation. Set CONDA_ROOT to the miniconda/anaconda root."
CONDA_SH="$CONDA_ROOT/etc/profile.d/conda.sh"
CONDA_ENV="${CONDA_ENV:-$CONDA_ROOT/envs/p3-cvrpsd}"

if [[ ! -f "$CONDA_SH" ]]; then
  fail_activate_env "Missing conda profile script: $CONDA_SH"
fi

source "$CONDA_SH"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  fail_activate_env "Missing requirements file: $REQUIREMENTS_FILE"
fi

echo "Creating conda environment: $CONDA_ENV" >&2
conda create -p "$CONDA_ENV" "python=$PYTHON_VERSION" -y
conda activate "$CONDA_ENV"

python -m pip install --upgrade pip
python -m pip install -r "$REQUIREMENTS_FILE"

if [[ -f "$GUROBI_LICENSE" ]]; then
  export GRB_LICENSE_FILE="$GUROBI_LICENSE"
fi
