#!/usr/bin/env bash

source /opt/python_envs/nupic/bin/activate

export APPHOME=/opt/predictors/nupic-predictor

export PYTHONPATH=/opt/predictors/nupic-predictor

cd $APPHOME/nupredictor

./nunetwork.py --server binarycapital.io --port 80 --create --magic 400 --username mellertson --password Outee411


