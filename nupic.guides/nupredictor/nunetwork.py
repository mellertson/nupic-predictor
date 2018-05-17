import re
import json
import os, errno, shutil
import yaml
import requests
from time import sleep
from dateutil import parser
from datetime import datetime, timedelta
import pytz
from nupic.engine import Network
from nupic.encoders import MultiEncoder
from nupic.data.file_record_stream import FileRecordStream
# from cerebro2.patcher import Patcher
import urllib
from optparse import OptionParser
import pandas as pd


class bcolors(object):
  HEADER = '\033[95m'
  OKBLUE = '\033[94m'
  OKGREEN = '\033[92m'
  WARNING = '\033[93m'
  FAIL = '\033[91m'
  ENDC = '\033[0m'
  BOLD = '\033[1m'
  UNDERLINE = '\033[4m'


def create_directory(full_path):
  """
  Checks to see if the directory exists, if it does not the directory is created

  :param full_path:
  :type full_path: str
  :return: True - if the directory was created or already existed
    False - if the directory could not be created for any reason
  :rtype: bool
  """
  if not os.path.exists(full_path):
    try:
      os.makedirs(full_path)
    except OSError as e:
      if e.errno != errno.EEXIST:
        return False

  # if the directory was created, or already exists, return True
  # to indicate that the directory is there and can be used by the system
  return True


def file_exists(full_path):
  """
    Tests to see if the fully qualified file exists

    :param full_path:
    :type full_path: str
    :return: True - if the file exists
      False - if the file does not exist
    :rtype: bool
    """
  # if the file exists...
  if os.path.exists(full_path):
    return True

  # if the file does NOT exist...
  else:
    return False


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


def initialize_csv(fq_input_filename):
  """
  Creates the input filename, initializing its top three rows in the Nupic file format

  NOTE: The "input file" will be over-written if it exists. If it does
  not exist, it will be created.

  :param fq_input_filename: The fully qualified path to the "input file"
  :type fq_input_filename: str
  :rtype: None
  """
  # write the headers
  lines = list()
  lines.append('timestamp, consumption\n')
  lines.append('datetime, float\n')
  lines.append('T, \n')

  # save the data to a .csv file
  with open(fq_input_filename, 'w') as f:
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
    return timedelta(hours=24)
  else:
    raise ValueError("{} is an invalid value".format(time_units))


def get_start_dates(start_dt, data_points, time_units):
  """
  :param start_dt:
  :type start_dt: datetime
  :param data_points:
  :type data_points: int
  :param time_units: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :rtype: list
  """
  dates = [start_dt]
  td = add_time(time_units=time_units) * 500
  blocks = int(data_points / 500.0)
  for i in range(blocks - 1):
    dates.append(start_dt + td * (i+1))
  return dates


def create_output_directory(fq_model_template_filename, fq_model_filename, model_output_files_dir):
  """
  Creates the experiment's output directory, and copies the Nupic template to the output directory

  The Nupic template is copied into the output directory and renamed to the 'fq_model_filename' parameter.
  All permission bits are copied from the tempalte file to the model file.  The file contents,
  owner, and groups are unaffected.

  :param fq_model_template_filename: The fully qualified filename of the YAML model to rename
    and copy into the output directory
  :type fq_model_template_filename: str
  :param fq_model_filename: The fully qualified YAML model file, for the Nupic model (a.k.a. Network)
  :type fq_model_filename: str
  :param model_output_files_dir: The fully qualified directory name to be created for the experiment
  :type model_output_files_dir: str
  :rtype: None
  """
  # create the experiment's output directory
  create_directory(full_path=model_output_files_dir)

  # copy the Nupic model "template" file to a unique filename,
  # located in the experiment's output directory
  shutil.copyfile(src=fq_model_template_filename, dst=fq_model_filename)

  # copy the permission bits from the tempalte filename to the
  # model filename in the output directory
  shutil.copymode(src=fq_model_template_filename, dst=fq_model_filename)


def cache_input_data_file(fq_input_filename, exchange, market, data_table, start, end, time_units, username='mellertson', password='test', host='localhost', port=8000,):
  """
  Get data from Django web-service, creating the input file if it does not exist

  :param fq_input_filename: The CSV file containing the input data to run through the Nupic model
  :type fq_input_filename: str
  :param exchange:
  :type exchange: str
  :param market:
  :type market: str
  :param data_table: The Django data model (table name) the data originates from
  :type data_table: str
  :param start:
  :type start: datetime
  :param end:
  :type end: datetime
  :param time_units: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :param username:
  :type username: str
  :param password:
  :type password: str
  :param host:
  :type host: str
  :param port:
  :type port: int
  :return:
  """
  # if file_exists(full_path=fq_input_filename):
  #     return

  # local variables
  global ACTUALS

  # Create the input file, over-writing it if it exists
  initialize_csv(fq_input_filename=fq_input_filename)

  # build the base url
  base_url = 'http://{}:{}/ws/data/get'.format(host, port)

  # build the input variables needed by the web-service
  params = {'username': username, 'passwd': password, 'exchange': exchange, 'symbol': market, 'data_table': data_table, 'start': start, 'end': end, 'time_units': time_units}

  # send the HTTP request and decode the JSON response
  response = requests.get(base_url, params=params, timeout=60*60)
  data = json.loads(response.content.decode('utf-8'))

  # write the lines of data
  lines = []
  for i, row in enumerate(data):
    # extract the variables from the row
    exchange = row['exchange']
    market = row['market']
    bid_price = float(row['bid_price'])
    bid_size = float(row['bid_size'])
    ask_price = float(row['ask_price'])
    ask_size = float(row['ask_size'])
    timestamp = parser.parse(row['timestamp'])
    try:
      value_to_predict = (ask_price - bid_price)
    except ZeroDivisionError:
      value_to_predict = 0.0

    # # add the actual value and timestamp to the global variables
    # timestamps.append(timestamp)
    # actuals.append(value_to_predict)

    # add the line we just built to 'lines' for output in a moment
    lines.append('{}, {:.15}\n'.format(timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"), value_to_predict))

  # save 'lines' to the CSV file
  with open(fq_input_filename, 'a+') as f:
    f.writelines(lines)


def cache_input_data_file_2(fq_input_filename, exchange, market, data_table, start, end, time_units, username='mellertson', password='test', host='localhost', port=8000, market2=None):
  """
  Get data from Django web-service, creating the input file if it does not exist

  :param fq_input_filename: The CSV file containing the input data to run through the Nupic model
  :type fq_input_filename: str
  :param exchange:
  :type exchange: str
  :param market:
  :type market: str
  :param market2:
  :type market2: str
  :param data_table: The Django data model (table name) the data originates from
  :type data_table: str
  :param start:
  :type start: datetime
  :param end:
  :type end: datetime
  :param time_units: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :param username:
  :type username: str
  :param password:
  :type password: str
  :param host:
  :type host: str
  :param port:
  :type port: int
  :return:
  """

  # local variables
  global ACTUALS

  # Create the input file, over-writing it if it exists
  initialize_csv(fq_input_filename=fq_input_filename)

  # build the base url
  base_url = 'http://{}:{}/ws/data/get'.format(host, port)

  # build the input variables needed by the web-service
  params1 = {'username': username, 'passwd': password, 'exchange': exchange, 'symbol': market, 'data_table': data_table, 'start': start, 'end': end, 'time_units': time_units}
  params2 = {'username': username, 'passwd': password, 'exchange': exchange, 'symbol': market2, 'data_table': data_table, 'start': start, 'end': end, 'time_units': time_units}

  # send the HTTP request and decode the JSON response
  response1 = requests.get(base_url, params=params1, timeout=60*60)
  response2 = requests.get(base_url, params=params2, timeout=60*60)
  # data1 = json.loads(response1.content.decode('utf-8'))
  # data2 = json.loads(response2.content.decode('utf-8'))
  data1 = pd.read_json(response1.content, orient='index', precise_float=True)
  data2 = pd.read_json(response2.content, orient='index', precise_float=True)

  # write the lines of data
  lines = []
  for ts, row in data1.iterrows():

    # extract the variables from the row
    m1_price = (float(row['ask_price']) + float(row['bid_price'])) / 2.0
    try:
      m2_price = (float(data2.loc[ts]['ask_price']) + float(data2.loc[ts]['bid_price'])) / 2.0
    except KeyError:
      m2_price = m1_price
    value_to_predict = (m1_price - m2_price) / m1_price * 100.0 if m1_price != 0.0 else 0.0
    if value_to_predict == 0.0:
      continue

    # add the line we just built to 'lines' for output in a moment
    lines.append('{}, {:.15}\n'.format(ts.strftime("%Y-%m-%d %H:%M:%S.%f"), value_to_predict))

  # save 'lines' to the CSV file
  with open(fq_input_filename, 'a+') as f:
    f.writelines(lines)


def read_input_file(fq_input_filename):
  """
  Read the input data file into local variables

  Read the input data file into local variables, so the
  nupic predictor can use them to make its predictions

  :param fq_input_filename: The fully qualified file name to the input data file
  :type fq_input_filename: str
  :rtype: None
  """
  global ACTUALS, TIMESTAMPS

  with open(fq_input_filename, 'r') as f:
      # skip first 3 lines (header rows)
      f.readline()
      f.readline()
      f.readline()

      line = f.readline()
      i = 0
      while line != '':
          row = line.split(',')
          timestamp = parser.parse(row[0])
          value_to_predict = float(row[1].split('\n')[0])

          # add timestamp and value to their respective lists
          TIMESTAMPS.append(timestamp)
          ACTUALS.append(value_to_predict)

          # read in the next line
          line = f.readline()
          i += 1
          if i % 500 == 0:
              print("Read {} lines...".format(i))

  print('Done reading the input file.')


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


def createNetwork(dataSource, fq_model_filename):
  """
  Create and initialize the Nupic model (a.k.a. Network)

  :param dataSource: The input data source for the Nupic model
  :type dataSource: FileRecordStream
  :param fq_model_filename: The fully qualified Nupic model filename
  :type fq_model_filename: str
  :returns: A fully initialized Nupic model (a.k.a. Network)
  :rtype: Network
  """
  with open(fq_model_filename, "r") as f:
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


def configureNetwork(network):
  """
  Configure the Nupic network

  Does the following:
    - sets the "predicted field" found in the data source
    - turns on learning mode for all regions in the network
    - turns on "inference mode" for all regions in the network

  :param network: A fully initialized Nupic model (a.k.a. Network)
  :type network: Network
  :rtype: None
  """
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


def run_the_predictor(fq_input_filename, fq_model_filename, fq_results_filename):
  """
  run the Nupic predictor, save the results to the 'model_output_files' directory

  :param fq_input_filename: The fully qualified path to the Nupic formatted input file name
  :type fq_input_filename: str
  :param fq_model_filename: The fully qualified path to the Nupic model parameters (in YAML format)
  :type fq_model_filename: str
  :param fq_results_filename: The fully qualified filename to store the results in
  :type fq_results_filename: str
  :return:
  """

  # create the CSV file
  global ACTUALS
  global UP
  global DOWN
  global EXCHANGE
  global BASE_DIR

  last_actual = 0.0
  last_prediction = 0.0
  toggle = 1000
  is_learning = True
  all_results = []
  scores = []
  row_col_len = len(str(DATA_POINTS))

  # Create a data source for the network.
  dataSource = FileRecordStream(streamID=fq_input_filename)
  numRecords = dataSource.getDataRowCount()
  network = createNetwork(dataSource=dataSource, fq_model_filename=fq_model_filename)

  # Configure the network according to the model parameters
  configureNetwork(network=network)

  # pop one item off the top of the actuals and timestamps, so the
  # actual and predicted values will line up
  del(ACTUALS[0])
  del(TIMESTAMPS[0])
  ACTUALS.append(0.0)
  TIMESTAMPS.append(TIMESTAMPS[-1] + timedelta(minutes=5))

  with open(fq_results_filename, 'w+') as out_file:
    # output results file header
    header = ','.join(['Row', 'Timestamp',
              'Actual', 'Actual Change', 'Actual Direction',
              'Prediction', 'Predicted Change', 'Predicted Direction',
              'Correct', 'Score',
              'Error', 'Confidence'])
    header += '\n'
    out_file.write(header)
    print(header)
    N = 1  # Run the network, N iterations at a time.
    for iteration in range(0, numRecords, N):
      actual = ACTUALS[iteration]

      # make predictions
      network.run(N)

      # extract the prediction
      predictionResults = getPredictionResults(network, "classifier")
      prediction = predictionResults[1]["predictedValue"]
      oneStepConfidence = predictionResults[1]["predictionConfidence"]

      ###################################################################################################
      # calculate error and actuals VS predicted
      error = (actual - prediction) / actual * 100 if abs(actual) > 0 else 0.0
      actual_change = (actual - last_actual) / actual * 100 if abs(actual) > 0 else 0.0
      predicted_change = (prediction - last_actual) / last_actual * 100 if iteration > 0 else 0.0

      ###################################################################################################
      # calculate the actual direction VS predicted direction
      actual_dir_colored = "who knows"
      predicted_dir_colored = "who knows"
      correct_colored = "who knows"
      if iteration > 0:
        actual_dir_colored = '{}'.format(UP) if actual_change > 0 else '{}'.format(DOWN)
        predicted_dir_colored = '{}'.format(UP) if predicted_change > 0 else '{}'.format(DOWN)
        correct_colored = '{}'.format(RIGHT) if actual_dir_colored == predicted_dir_colored else '{}'.format(WRONG)
        actual_dir = '{}'.format('Up') if actual_change > 0 else '{}'.format('Down')
        predicted_dir = '{}'.format('Up') if predicted_change > 0 else '{}'.format('Down')
        correct = '{}'.format('Right') if actual_dir == predicted_dir else '{}'.format('Wrong')
      else:
        correct = predicted_dir = actual_dir = '          '

      # store the actual and prediction
      all_results.append({'actual': actual, 'prediction': prediction, 'error': error})
      scores.append(1.0 if correct == 'Right' else 0.0)

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
      msg = "Row {}:\t{}\t".format(row, TIMESTAMPS[iteration])
      msg += "actual value:{:14.8f} {:12.4f}% {}\t".format(actual, actual_change, actual_dir_colored)
      msg += "predicted value:{:14.8f} {:12.4f}% {}\t".format(prediction, predicted_change, predicted_dir_colored)
      msg += "{}\t".format(correct_colored)
      msg += "score: {:.2f}%\t".format(score)
      msg += "error: {:.2f}%\t".format(avg_pct_error)
      msg += "confidence: {:.2f}%\t".format(oneStepConfidence * 100)
      print(msg)

      # Write results to output file
      msg = "{},{},".format(iteration + 1, TIMESTAMPS[iteration])
      msg += "{:.8f},{:.4f},{},".format(actual, actual_change, actual_dir)
      msg += "{:.8f},{:.4f},{},".format(prediction, predicted_change, predicted_dir)
      msg += "{},".format(correct)
      msg += "{:.1f},".format(score)
      msg += "{:.2f},".format(avg_pct_error)
      msg += "{:.8f}".format(oneStepConfidence * 100)
      if iteration == 0:
        msg = msg.replace('          ', '')
      out_file.write(msg + '\n')

      # store values for next iteration
      last_actual = actual
      # last_prediction = prediction

  # copy the results file, so it can be plotted
  shutil.copyfile(fq_results_filename, os.path.join(BASE_DIR, 'results.csv'))


global EXPERIMENT_NAME, INPUT_FILENAME, RESULTS_FILENAME, MODEL_FILENAME, BASE_DIR, MODEL_INPUT_FILES_DIR
global MODEL_OUTPUT_FILES_DIR, FQ_RESULTS_FILENAME, FQ_MODEL_FILENAME, FQ_MODEL_TEMPLATE_FILENAME

# Input variables into the system
EXCHANGE = 'bitmex'
NMARKET = 'XBTM18'.lower()
MARKET2 = 'XBTUSD'.lower()
DATA_TABLE = 'quote'
SUFFIX_NAME = 'bid.ask.spread-as-pct-change'
CURRENT_DATE_TIME = datetime.now().strftime("%Y.%m.%d.%I.%M.%p").lower()
# CANDLESTICK_SIZE = '1h' # 1m = 1 minute, 5m = 5 minutes
START_DATE = datetime(2015, 10, 1, tzinfo=pytz.utc)
END_DATE = datetime(2018, 4, 1, tzinfo=pytz.utc)
DATA_POINTS = int((END_DATE - START_DATE).total_seconds() / 60 / 5) + 1

# INPUT and OUTPUT file names
EXPERIMENT_NAME = '{}.{}.{}.{}.{}'.format(CURRENT_DATE_TIME, EXCHANGE, NMARKET, DATA_TABLE, SUFFIX_NAME)
INPUT_FILENAME = '{}.{}.{}.csv'.format(EXCHANGE, NMARKET, DATA_TABLE)
RESULTS_FILENAME = '{}.results.csv'.format(EXPERIMENT_NAME)
MODEL_FILENAME = '{}.model.yaml'.format(EXPERIMENT_NAME)

# INPUT and OUTPUT directory names
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_INPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_input_files')
MODEL_OUTPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_output_files/{}'.format(EXPERIMENT_NAME))
# FQ_INPUT_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, INPUT_FILENAME)
FQ_RESULTS_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, RESULTS_FILENAME)
FQ_MODEL_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, MODEL_FILENAME)
FQ_MODEL_TEMPLATE_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, "model-template.yaml")

# Output variables
ACTUALS = []
TIMESTAMPS = []

# unicode characters
UP_CHAR = unichr(8593).encode('utf-8')
DOWN_CHAR = unichr(8595).encode('utf-8')
RIGHT_CHAR = unichr(10003).encode('utf-8')
WRONG_CHAR = unichr(215).encode('utf-8')

# colored messages   BOLD = '\033[1m'    '\033[94m'      8593
UP = '{}{}{} Bigger {}'.format(bcolors.BOLD, bcolors.OKBLUE, UP_CHAR, bcolors.ENDC)
DOWN = '{}{}{} Smaller{}'.format(bcolors.BOLD, bcolors.FAIL, DOWN_CHAR, bcolors.ENDC)
RIGHT = '{}{}{} Right {}'.format(bcolors.BOLD, bcolors.OKBLUE, RIGHT_CHAR, bcolors.ENDC)
WRONG = '{}{}{} Wrong {}'.format(bcolors.BOLD, bcolors.FAIL, WRONG_CHAR, bcolors.ENDC)


def parse_options():
  """
  Parse command line options and return them

  Valid command line options are:
    '-c' or "--create" - create the input file from data in the database
    '-f' or "--file"   - specify the fully qualified path to a CSV filename to use as input data
    '-s' or "--start"  - the start date to get data from, defaults to 10/01/2015
    '-e' or "--end"    - the end date to get data till, defaults to 04/01/2018"
    '-d' or "--server" - the name of the Django server to get the data from
    '-p' or "--port"   - (default = 80) the port number the Django server is running on
    '-m' or "--market" - the market symbol
    '-F' or "--future" - the second market to calculate the spread from
    '-t' or "--time_units" - the time units, either: "1m", "5m", "1h", "1d"

  :returns: (options, args)
  :rtype: tuple
  """

  usage = "usage: $prog [options]"
  parser = OptionParser(usage)
  parser.add_option('-c', "--create", dest="create_input_file", action="store_true", default=False,
                    help="create the input file from data in the database")
  parser.add_option('-f', "--file", dest="input_filename", default="{}/input_data.csv".format(MODEL_INPUT_FILES_DIR),
                    help="specify the fully qualified path to a CSV filename to use as input data")
  parser.add_option('-s', "--start", dest="start", default="2015-10-01",
                    help="the start date to get data from, defaults to 10/01/2015")
  parser.add_option('-e', "--end", dest="end", default="2018-4-01",
                    help="the end date to get data till, defaults to 04/01/2018")
  parser.add_option('-d', "--server", dest="server_name", default="codehammer",
                    help="the name of the Django server to get the data from")
  parser.add_option('-p', "--port", dest="server_port", default="80",
                    help="(default = 80) the port number the Django server is running on")
  parser.add_option('-m', "--market", dest="market1", default="BTC/USD",
                    help="(default = BTC/USD) the market symbol")
  parser.add_option('-F', "--future", dest="market2", default=None,
                    help="the second market to calculate the spread from")
  parser.add_option('-t', "--time_units", dest="time_units", default='5m',
                    help='the time units, either: "1m", "5m", "1h", "1d"')

  (options, args) = parser.parse_args()
  return options, args


if __name__ == "__main__":

  options, args = parse_options()
  create_input_file = options.create_input_file
  input_filename = options.input_filename
  start = parser.parse(options.start)
  end = parser.parse(options.end)
  django_server = options.server_name
  django_port = options.server_port
  market1_symbol = options.market1
  future_symbol = options.market2
  time_units = options.time_units

  # INPUT and OUTPUT file names
  nmarket = market1_symbol.lower().replace('/', '')
  EXPERIMENT_NAME = '{}.{}.{}.{}.{}'.format(CURRENT_DATE_TIME, EXCHANGE, nmarket, DATA_TABLE, SUFFIX_NAME)
  INPUT_FILENAME = '{}.{}.{}.csv'.format(EXCHANGE, nmarket, DATA_TABLE)
  RESULTS_FILENAME = '{}.results.csv'.format(EXPERIMENT_NAME)
  MODEL_FILENAME = '{}.model.yaml'.format(EXPERIMENT_NAME)

  # INPUT and OUTPUT directory names
  BASE_DIR = os.path.dirname(os.path.abspath(__file__))
  MODEL_INPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_input_files')
  MODEL_OUTPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_output_files/{}'.format(EXPERIMENT_NAME))
  FQ_RESULTS_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, RESULTS_FILENAME)
  FQ_MODEL_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, MODEL_FILENAME)
  FQ_MODEL_TEMPLATE_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, "model-template.yaml")

  # create the 'model_output_files' directory and copy the model template
  # file into the 'model_output_files' directory and rename it
  create_output_directory(fq_model_template_filename=FQ_MODEL_TEMPLATE_FILENAME,
                          fq_model_filename=FQ_MODEL_FILENAME,
                          model_output_files_dir=MODEL_OUTPUT_FILES_DIR)

  # if the input data file does not exist, get the data from
  # the Django server and cache it in a local CSV file in
  # the 'model_input_files' directory
  if create_input_file:
    if future_symbol is None:
      cache_input_data_file(fq_input_filename=input_filename,
                            exchange=EXCHANGE,
                            market=market1_symbol,
                            data_table=DATA_TABLE,
                            start=start,
                            end=end,
                            time_units=time_units,
                            host=django_server,
                            port=django_port)
    else:
      cache_input_data_file_2(fq_input_filename=input_filename,
                              exchange=EXCHANGE,
                              market=market1_symbol,
                              data_table=DATA_TABLE,
                              start=start,
                              end=end,
                              time_units=time_units,
                              host=django_server,
                              port=django_port,
                              market2=future_symbol)

  # read the input data file into local variables, so the
  # nupic predictor can use them to make its predictions
  if file_exists(input_filename):
    read_input_file(fq_input_filename=input_filename)
  else:
    raise ValueError("Filename '{}' does not exist".format(input_filename))

  # run the Nupic predictor, make the predictions, and
  # save the results to the 'model_output_files' directory
  run_the_predictor(fq_input_filename=input_filename,
                    fq_model_filename=FQ_MODEL_FILENAME,
                    fq_results_filename=FQ_RESULTS_FILENAME)








