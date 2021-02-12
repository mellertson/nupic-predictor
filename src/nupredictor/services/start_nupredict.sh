#!/usr/bin/env bash
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SRC_ROOT="$(dirname $SRC_ROOT)"
SRC_ROOT="$(dirname $SRC_ROOT)" #should set SRC_ROOT to spread-predictor/src
echo "SRC_ROOT = $SRC_ROOT"

source $SRC_ROOT/venv/bin/activate
export APPHOME="$(dirname $SRC_ROOT)"
export PYTHONPATH="$SRC_ROOT"
cd $APPHOME/nupredictor
./nunetwork.py --server example.com --port 80 --create --magic 400 --username my_username --password super_secret_password