import json
import os
import yaml



_EXAMPLE_DIR = os.path.dirname(os.path.abspath(__file__))
_PARAMS_PATH = os.path.join(_EXAMPLE_DIR, "2018.05.08.11.00.pm.xbtm18.bidprice.askprice.spread.model.yaml")
print('_PARAMS_PATH = {}'.format(_PARAMS_PATH))

with open(_PARAMS_PATH, "r") as f:
  modelParams = yaml.safe_load(f)["modelParams"]

print('modelParams = {}'.format(modelParams))