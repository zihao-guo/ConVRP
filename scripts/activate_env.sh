#!/usr/bin/env bash
set -eo pipefail

CONDA_SH="/home/zeio99/miniconda3/etc/profile.d/conda.sh"
CONDA_ENV="/home/zeio99/miniconda3/envs/p3-cvrpsd"
GUROBI_LICENSE="/mnt/c/Users/User/Downloads/gurobi.lic"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Missing conda profile script: $CONDA_SH" >&2
  exit 1
fi

if [[ ! -d "$CONDA_ENV" ]]; then
  echo "Missing conda environment: $CONDA_ENV" >&2
  exit 1
fi

source "$CONDA_SH"
conda activate "$CONDA_ENV"

if [[ -f "$GUROBI_LICENSE" ]]; then
  export GRB_LICENSE_FILE="$GUROBI_LICENSE"
fi
