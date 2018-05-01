import re
import json
import os
import yaml
import requests
from time import sleep
from dateutil import parser
from datetime import datetime, timedelta
from nupic.engine import Network
from nupic.encoders import MultiEncoder
from nupic.data.file_record_stream import FileRecordStream


class bcolors(object):
  HEADER = '\033[95m'
  OKBLUE = '\033[94m'
  OKGREEN = '\033[92m'
  WARNING = '\033[93m'
  FAIL = '\033[91m'
  ENDC = '\033[0m'
  BOLD = '\033[1m'
  UNDERLINE = '\033[4m'


def calculate_start_date(end_date, data_points, time_units):
  """

  :param end_date:
  :type end_date: datetime
  :param data_points:
  :type data_points: int
  :param time_units: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :return:
  """
  td = add_time(time_units=time_units)
  start_date = end_date - (td * data_points)
  return start_date


def initialize_csv():
  # write the headers
  lines = list()
  lines.append('timestamp, consumption\n')
  lines.append('datetime, float\n')
  lines.append('T, \n')

  # save the data to a .csv file
  with open(INPUT_FILE_PATH, 'w') as f:
    f.writelines(lines)


def add_time(time_units):
  """
  :param time_units: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :returns: 'm' | 'h' \ 'd'
  :rtype: timedelta
  """
  m1_ptn = re.compile(r'^1m$')
  m5_ptn = re.compile(r'^5m$')
  h_ptn = re.compile(r'^1h$')
  d_ptn = re.compile(r'^1d$')
  if m1_ptn.search(time_units):
    return timedelta(minutes=1)
  elif m5_ptn.search(time_units):
    return timedelta(minutes=5)
  elif h_ptn.search(time_units):
    return timedelta(hours=1)
  elif d_ptn.search(time_units):
    return timedelta(days=1)
  else:
    raise ValueError("{} is an invalid value".format(time_units))


def get_start_dates(start_dt):
  """
  :param start_dt:
  :type start_dt: datetime
  :rtype: list
  """
  dates = [start_dt]
  td = add_time(CANDLESTICK_SIZE) * 500
  blocks = int(DATA_POINTS / 500.0)
  for i in range(blocks - 1):
    dates.append(start_dt + td * (i+1))
  return dates


def get_data(start_dt):
  """
  :param start_dt:
  :type start_dt: datetime
  :return:
  """
  # local variables
  fmt = "%Y-%m-%dT%H:%M:%S.000Z"
  dates = get_start_dates(start_dt=start_dt)

  # initialize the CSV file
  initialize_csv()

  for start in dates:
    start = start.strftime(fmt).replace(":", "%3A")
    url = 'https://www.bitmex.com/api/v1/quote/bucketed?binSize=1m&partial=false&symbol={}&count=500&reverse=false&startTime={}'.format(MARKET, start)
    response = requests.get(url)
    data = json.loads(response.content.decode('utf-8'))

    # write the lines of data
    lines = []
    for i in range(len(data)):
      timestamp = parser.parse(data[i]['timestamp'])
      timestamps.append(timestamp)
      bid_price = float(data[i]['bidPrice'])
      ask_price = float(data[i]['askPrice'])
      spread_pct_diff = (ask_price - bid_price) / ask_price * 100
      actuals.append(spread_pct_diff)
      lines.append('{}, {:.15}\n'.format(timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"), spread_pct_diff))

    # save the data to a .csv file
    with open(INPUT_FILE_PATH, 'a+') as f:
      f.writelines(lines)

    # sleep so we don't hit Bitmex's rate limit
    sleep(2)


def createDataOutLink(network, sensorRegionName, regionName):
  """Link sensor region to other region so that it can pass it data."""
  network.link(sensorRegionName, regionName, "UniformLink", "",
               srcOutput="dataOut", destInput="bottomUpIn")


def createFeedForwardLink(network, regionName1, regionName2):
  """Create a feed-forward link between 2 regions: regionName1 -> regionName2"""
  network.link(regionName1, regionName2, "UniformLink", "",
               srcOutput="bottomUpOut", destInput="bottomUpIn")


def createResetLink(network, sensorRegionName, regionName):
  """Create a reset link from a sensor region: sensorRegionName -> regionName"""
  network.link(sensorRegionName, regionName, "UniformLink", "",
               srcOutput="resetOut", destInput="resetIn")


def createSensorToClassifierLinks(network, sensorRegionName,
                                  classifierRegionName):
  """Create required links from a sensor region to a classifier region."""
  network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
               srcOutput="bucketIdxOut", destInput="bucketIdxIn")
  network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
               srcOutput="actValueOut", destInput="actValueIn")
  network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
               srcOutput="categoryOut", destInput="categoryIn")

def createEncoder(encoderParams):
  """Create a multi-encoder from params."""
  encoder = MultiEncoder()
  encoder.addMultipleEncoders(encoderParams)
  return encoder


def createNetwork(dataSource):
  """Create and initialize a network."""
  with open(PARAMS_PATH, "r") as f:
    modelParams = yaml.safe_load(f)["modelParams"]

  # Create a network that will hold the regions
  network = Network()

  ################################################################################
  # Sensor Region
  ################################################################################
  # Add a sensor region
  network.addRegion("sensor", "py.RecordSensor", '{}')

  # Set the encoder and data source of the sensor region.
  sensorRegion = network.regions["sensor"].getSelf()
  sensorRegion.encoder = createEncoder(modelParams["sensorParams"]["encoders"])
  sensorRegion.dataSource = dataSource

  ################################################################################
  # Synchronize Sensor Region output width with Spatial Pooler input width
  ################################################################################
  modelParams["spParams"]["inputWidth"] = sensorRegion.encoder.getWidth()

  ################################################################################
  # SP and TM Regions
  ################################################################################
  # Add SP and TM regions
  network.addRegion("SP", "py.SPRegion", json.dumps(modelParams["spParams"]))
  network.addRegion("TM", "py.TMRegion", json.dumps(modelParams["tmParams"]))

  ################################################################################
  # Classifier Region
  ################################################################################
  # Add a classifier region
  clName = "py.%s" % modelParams["clParams"].pop("regionName")
  network.addRegion("classifier", clName, json.dumps(modelParams["clParams"]))

  ################################################################################
  # Link the Regions
  ################################################################################
  # Add all links
  createSensorToClassifierLinks(network, "sensor", "classifier")
  createDataOutLink(network, "sensor", "SP")
  createFeedForwardLink(network, "SP", "TM")
  createFeedForwardLink(network, "TM", "classifier")
  # Reset links are optional, since the sensor region does not send resets
  createResetLink(network, "sensor", "SP")
  createResetLink(network, "sensor", "TM")

  ################################################################################
  # Initialize the Network
  ################################################################################
  # Make sure all objects are initialized
  network.initialize()

  return network


def getPredictionResults(network, clRegionName):
  """Get prediction results for all prediction steps."""
  classifierRegion = network.regions[clRegionName]
  actualValues = classifierRegion.getOutputData("actualValues")
  probabilities = classifierRegion.getOutputData("probabilities")
  steps = classifierRegion.getSelf().stepsList
  N = classifierRegion.getSelf().maxCategoryCount
  results = {step: {} for step in steps}
  for i in range(len(steps)):
    # stepProbabilities are probabilities for this prediction step only.
    stepProbabilities = probabilities[i * N:(i + 1) * N - 1]
    mostLikelyCategoryIdx = stepProbabilities.argmax()
    predictedValue = actualValues[mostLikelyCategoryIdx]
    predictionConfidence = stepProbabilities[mostLikelyCategoryIdx]
    results[steps[i]]["predictedValue"] = predictedValue
    results[steps[i]]["predictionConfidence"] = predictionConfidence
  return results


def enableLearning(network):
  # Enable learning for all regions.
  network.regions["SP"].setParameter("learningMode", 1)
  network.regions["TM"].setParameter("learningMode", 1)
  network.regions["classifier"].setParameter("learningMode", 1)


def disableLearning(network):
  # Enable learning for all regions.
  network.regions["SP"].setParameter("learningMode", 0)
  network.regions["TM"].setParameter("learningMode", 0)
  network.regions["classifier"].setParameter("learningMode", 0)


def runHotgym(start_date):
  """Run the Hot Gym example."""

  # create the CSV file
  global actuals
  global bigger
  global smaller

  get_data(start_date)
  last_actual = 0.0
  last_prediction = 0.0
  all_results = []
  scores = []
  row_col_len = len(str(DATA_POINTS))

  # Create a data source for the network.
  dataSource = FileRecordStream(streamID=INPUT_FILE_PATH)
  numRecords = dataSource.getDataRowCount()
  network = createNetwork(dataSource)

  # Set predicted field.
  network.regions["sensor"].setParameter("predictedField", "consumption")

  # Enable learning for all regions.
  network.regions["SP"].setParameter("learningMode", 1)
  network.regions["TM"].setParameter("learningMode", 1)
  network.regions["classifier"].setParameter("learningMode", 1)

  # Enable inference for all regions.
  network.regions["SP"].setParameter("inferenceMode", 1)
  network.regions["TM"].setParameter("inferenceMode", 1)
  network.regions["classifier"].setParameter("inferenceMode", 1)

  with open(OUTPUT_FILE_PATH, 'w+') as out_file:
    # output results file header
    header = 'Nupic Predicting {} Order Book Spread on Bitmex\n\n'.format(MARKET)
    out_file.write(header)
    print(header)
    N = 1  # Run the network, N iterations at a time.
    for iteration in range(0, numRecords, N):
      actual = actuals[iteration]

      # make predictions
      network.run(N)

      # extract the prediction
      predictionResults = getPredictionResults(network, "classifier")
      prediction = predictionResults[1]["predictedValue"]
      oneStepConfidence = predictionResults[1]["predictionConfidence"]

      # calculate stats on the prediction VS actual
      error = (actual - prediction) / actual * 100 if abs(actual) > 0 else 0.0
      actual_change = (actual - last_actual) / actual * 100 if abs(actual) > 0 else 0.0
      predicted_change = (prediction - last_prediction) / prediction * 100 if iteration > 0 else 0.0

      # calculate the actual VS predicted directional movement
      if iteration > 0:
        actual_dir = '{}'.format(bigger) if actual_change > 0 else '{}'.format(smaller)
        predicted_dir = '{}'.format(bigger) if predicted_change > 0 else '{}'.format(smaller)
        correct = '{}'.format(right) if actual_dir == predicted_dir else '{}'.format(wrong)
      else:
        correct = predicted_dir = actual_dir = '          '

      # store the actual and prediction
      all_results.append({'actual': actual, 'prediction': prediction, 'error': error})
      scores.append(1.0 if correct == right else 0.0)

      # calculate the average percent error of the prediction
      avg_pct_error = 0.0
      for r in all_results:
        _error = r['error']
        avg_pct_error += _error
      avg_pct_error = avg_pct_error / len(all_results)

      # calculate the current score
      score = sum(scores) / len(scores) * 100

      # print out results
      row = '{}'.format(iteration + 1).rjust(row_col_len, ' ')
      msg = "Row {}:\t\t{}\t\t".format(row, timestamps[iteration])
      msg += "spread: {:.8f} {:10.4f}% {}\t\t".format(actual, actual_change, actual_dir)
      msg += "predicted: {:.8f} {:10.4f}% {}\t\t".format(prediction, predicted_change, predicted_dir)
      msg += "{}\t\t".format(correct)
      msg += "score: {:.2f}%\t\t".format(score)
      # msg += "error: {:8.4f}%\t\t".format(avg_pct_error)
      # msg += "confidence: {:8.4f}%\t\t".format(oneStepConfidence * 100)
      print(msg)

      # Write results to output file
      out_file.write(msg + '\n')

      # store values for next iteration
      last_actual = actual
      last_prediction = prediction


# Input variables into the system
MARKET = 'XBTUSD'
CANDLESTICK_SIZE = '1m' # 1m = 1 minute, 5m = 5 minutes
DATA_POINTS = 10000
END_DATE = datetime.utcnow()
START_DATE = calculate_start_date(end_date=END_DATE, data_points=DATA_POINTS, time_units=CANDLESTICK_SIZE)
INPUT_FILENAME = '{}.csv'.format(MARKET.lower())
OUTPUT_FILENAME = '{}-results.txt'.format(MARKET.lower())

# Constants
EXAMPLE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE_PATH = os.path.join(EXAMPLE_DIR, INPUT_FILENAME)
OUTPUT_FILE_PATH = os.path.join(EXAMPLE_DIR, OUTPUT_FILENAME)
PARAMS_PATH = os.path.join(EXAMPLE_DIR, "model.yaml")

# Output variables
actuals = [0.0]
timestamps = []

# unicode characters
up_char = unichr(8593).encode('utf-8')
down_char = unichr(8595).encode('utf-8')
right_char = unichr(10003).encode('utf-8')
wrong_char = unichr(215).encode('utf-8')

# colored messages
bigger =  '{}{}{} Bigger {}'.format(bcolors.BOLD, bcolors.OKBLUE, up_char, bcolors.ENDC)
smaller = '{}{}{} Smaller{}'.format(bcolors.BOLD, bcolors.FAIL, down_char, bcolors.ENDC)
right = '{}{}{} Right {}'.format(bcolors.BOLD, bcolors.OKBLUE, right_char, bcolors.ENDC)
wrong = '{}{}{} Wrong {}'.format(bcolors.BOLD, bcolors.FAIL, wrong_char, bcolors.ENDC)


if __name__ == "__main__":
  runHotgym(START_DATE)