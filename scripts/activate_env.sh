#!/usr/bin/env bash
set -eo pipefail

CONDA_SH="/home/zeio99/miniconda3/etc/profile.d/conda.sh"
CONDA_ENV="/home/zeio99/miniconda3/envs/p3-cvrpsd"
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

if [[ ! -f "$CONDA_SH" ]]; then
  fail_activate_env "Missing conda profile script: $CONDA_SH"
fi

source "$CONDA_SH"

if [[ ! -d "$CONDA_ENV" ]]; then
  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    fail_activate_env "Missing requirements file: $REQUIREMENTS_FILE"
  fi
  echo "Creating conda environment from scratch: $CONDA_ENV" >&2
  conda create -p "$CONDA_ENV" "python=$PYTHON_VERSION" -y
  conda activate "$CONDA_ENV"
  python -m pip install --upgrade pip
  python -m pip install -r "$REQUIREMENTS_FILE"
else
  conda activate "$CONDA_ENV"
fi

if [[ -f "$GUROBI_LICENSE" ]]; then
  export GRB_LICENSE_FILE="$GUROBI_LICENSE"
fi
