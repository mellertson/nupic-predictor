#!/opt/python_envs/nupic/bin/python
import re
import json
import os, errno, shutil
import yaml
import requests
from dateutil import parser
from datetime import datetime, timedelta
import pytz
from nupic.engine import Network
from nupic.encoders import MultiEncoder
from nupic.data.file_record_stream import FileRecordStream
from optparse import OptionParser
import pandas as pd
from nupredictor.functions import get_files
from nupredictor.utilities import parse_time_units
import tzlocal
from multiprocessing.connection import Client
from socket import getfqdn, gethostname

SUBSCRIBED = 1
UNSUBSCRIBED = 2
INVALID_REQUEST = 400


__all__ = [
  # global variables
  'BASE_DIR',
  'DATA_POINTS',
  'DATA_TABLE',
  'INPUT_FILENAME',
  'MODEL_INPUT_FILES_DIR',
  'START_DATE',
  
  # everything else
  'bcolors',
  'calculate_start_date',
  'fetch_market_data',
  'get_file_permissions',
  'get_start_dates',
  'initialize_csv',
  'modify_output_file_permissions',
  'write_input_file',
  'get_services',
]


class Prediction(object):
  def __init__(self, time_predicted, exchange, market, time_units,
               prediction_type, prediction, confidence, actual, pct_error):
    self.time_predicted = time_predicted
    self.exchange = exchange
    self.market = market
    self.time_units = time_units
    self.prediction_type = prediction_type
    self.prediction = prediction
    self.confidence = confidence
    self.actual = actual
    self.pct_error = pct_error


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


def fetch_market_data(exchange, markets, data_table, start, end, time_units,
                      username='mellertson', password='test', host='localhost', port=8000):
  """
  Get data from Django web-service

  :param exchange:
  :type exchange: str
  :param markets: list of market symbols
  :type markets: list(str, str, ...)
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
  :return: Pandas DataFrames, e.g.: {'BTC/USD': dataframe, 'BTC/M18': dataframe}
  :rtype: dict
  """

  # local variables
  base_url = 'http://{}:{}/ws/data/get'.format(host, port)
  frames = {}

  # for each market...
  for market in markets:
    # build the input variables needed by the web-service
    params1 = {'username': username, 'passwd': password, 'exchange': exchange, 'symbol': market,
               'data_table': data_table, 'start': start, 'end': end, 'time_units': time_units}

    # send the HTTP request and decode the JSON response
    response = requests.get(base_url, params=params1, timeout=60*60)
    if response.status_code != 200:
      raise ValueError('No {}-{} data was found between {} and {} for {}'
                       .format(exchange, market, start, end, time_units))
    data = pd.read_json(response.content, orient='record', precise_float=True)

    # verify there is at least 1 row of data in each data set
    if len(data) < 1:
      raise ValueError('No {}-{} data was found between {} and {} for {}'
                       .format(exchange, market, start, end, time_units))

    frames[market] = data

  # calculate start and end dates
  start = datetime(1973, 1, 18)
  end = datetime(2500, 1, 18)
  for market, df in frames.items():
    s = min(df['timestamp'])
    e = max(df['timestamp'])
    start = s if s > start else start
    end = e if e < end else end

  # slice down the data frames to the common start and end dates
  for market, df in frames.items():
    df = df.set_index('timestamp')
    frames[market] = df[start:end]

    # slice down the data to the MAGIC NUMBER of records
    frames[market] = frames[market][-MAGIC_N:]

  # return the data frames
  return frames


def initialize_csv(fq_input_filename, markets, include_spread=True, include_classification=False):
  """
  Creates the input filename, initializing its top three rows in the Nupic file format

  NOTE: The "input file" will be over-written if it exists. If it does
  not exist, it will be created.

  :param fq_input_filename: The fully qualified path to the "input file"
  :type fq_input_filename: str
  :param include_spread:
  :type include_spread: bool
  :param markets: The list of markets which will be included in the input file, e.g.: 'BTC/USD' | 'BTC/M18'
  :type markets: list(str, str, ...)
  :param include_classification:
  :type include_classification: bool
  :rtype: None
  """

  price_fields = ['open', 'high', 'low', 'close', 'volume', 'lastSize']
  fields = ['timestamp']   # the list of field names to be included in the input file
  dtypes = ['datetime']
  thirds = ['T']

  # build the list of fields that will be included in the input file
  # if include_spread:
  #   fields.append('spread')
  #   dtypes.append('float')
  #   thirds.append(' ')
  # if include_classification:
  #   fields.append('classification')
  #   dtypes.append('int')
  #   thirds.append(' ')
  for market in markets:
    m = market.replace('/', '').lower()
    for field in price_fields:
      fields.append('{}_{}'.format(m, field))
      dtypes.append('float')
      thirds.append(' ')

  # write the headers
  lines = list()
  lines.append(', '.join(fields) + '\n')
  lines.append(', '.join(dtypes) + '\n')
  lines.append(', '.join(thirds) + '\n')

  # save the data to a .csv file
  with open(fq_input_filename, 'w') as f:
    f.writelines(lines)


def write_input_file(fq_input_filename, markets, market_data, include_spread=True,
                     spread_as_pct=False, include_classification=False):
  """
  Create the input file from given market data

  :param fq_input_filename: The CSV file containing the input data to run through the Nupic model
  :type fq_input_filename: str
  :param markets: Example: ['BTC/USD', 'BTC/M18']
  :type markets: list
  :param market_data: Example: {'BTC/USD': dataframe, 'BTC/M18': dataframe}
  :type market_data: dict
  :param include_spread:
  :type include_spread: bool
  :param spread_as_pct:
  :type spread_as_pct: bool
  :param include_classification:
  :type include_classification: bool
  :return:
  """

  # save 'lines' to the CSV file
  with open(fq_input_filename, 'a+') as f:
    for market in markets:
      for ts, row in market_data[market].iterrows():
        line = list()

        # add the timestamp to the first column of the line
        line.append(ts.strftime("%Y-%m-%d %H:%M:%S.%f"))

        # extract the variables from the row
        open_price = float(row['open'])
        high = float(row['high'])
        low = float(row['low'])
        close = float(row['close'])
        volume = float(row['volume'])
        lastSize = float(row['lastSize'])
        # if spread_as_pct:
        #   spread = (ask_price - bid_price) / ask_price * 100.0 if ask_price != 0.0 else 0.0
        # else:
        #   spread = ask_price - bid_price

        # calculate the classification of the spread
        # if spread >= 2.0:
        #   classification = 5
        # elif spread < 2.0 and spread >= 1.0:
        #   classification = 4
        # elif spread < 1.0 and spread > -1.0:
        #   classification = 3
        # elif spread <= -1.0 and spread > -2.0:
        #   classification = 2
        # else:
        #   classification = 1

        # append the values to the line
        # if include_spread:
        #   line.append(str(spread))
        # if include_classification:
        #   line.append(str(classification))
        line.append(str(open_price))
        line.append(str(high))
        line.append(str(low))
        line.append(str(close))
        line.append(str(volume))
        line.append(str(lastSize))

        # write the line into the file
        f.write(','.join(line) + '\n')


def get_file_permissions(fq_filename):
  """
  Returns a file's permission mask

  :param fq_filename: A fully qualified filename
  :type fq_filename: str
  :return: Example: 644
  :rtype: str
  """
  return oct(os.stat(fq_filename)[0])[4:]


def modify_output_file_permissions(fq_output_dir):
  """
  Makes all files in the output directory read/writable by all users

  :param fq_output_dir:
  :type fq_output_dir: str
  :return:
  """

  # get the list of files in the output directory
  files = get_files(fq_output_dir)

  # change the permissions of all files in the output directory
  for file in files:
    fq_file = os.path.join(fq_output_dir, file)
    cmd = 'chmod o+rw {}'.format(fq_file)
    os.system(cmd)


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


def configureNetwork(network, predicted_field):
  """
  Configure the Nupic network

  Does the following:
    - sets the "predicted field" found in the data source
    - turns on learning mode for all regions in the network
    - turns on "inference mode" for all regions in the network

  :param network: A fully initialized Nupic model (a.k.a. Network)
  :type network: Network
  :param predicted_field: The "fieldname", identified in the model parameters file, which will be predicted, e.g. "spread" or "m1_ask"
  :type predicted_field: str
  :rtype: None
  """
  # Set predicted field.
  network.regions["sensor"].setParameter("predictedField", predicted_field)

  # Enable learning for all regions.
  network.regions["SP"].setParameter("learningMode", 1)
  network.regions["TM"].setParameter("learningMode", 1)
  network.regions["classifier"].setParameter("learningMode", 1)

  # Enable inference for all regions.
  network.regions["SP"].setParameter("inferenceMode", 1)
  network.regions["TM"].setParameter("inferenceMode", 1)
  network.regions["classifier"].setParameter("inferenceMode", 1)


def run_the_predictor(fq_input_filename, fq_model_filename, fq_results_filename, predicted_field,
                      market, prediction_type, time_units):
  """
  run the Nupic predictor, save the results to the 'model_output_files' directory

  :param fq_input_filename: The fully qualified path to the Nupic formatted input file name
  :type fq_input_filename: str
  :param fq_model_filename: The fully qualified path to the Nupic model parameters (in YAML format)
  :type fq_model_filename: str
  :param fq_results_filename: The fully qualified filename to store the results in
  :type fq_results_filename: str
  :param predicted_field: The "fieldname", identified in the model parameters file, which will be predicted, e.g. "spread" or "m1_ask"
  :type predicted_field: str
  :param market:
  :type market: str
  :param prediction_type:
  :type prediction_type: str
  :param time_units: Either: '1m' | '5m' | '1h' | '1d'
  :type time_units: str
  :return:
  :rtype: Prediction
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
  tz_local = tzlocal.get_localzone()
  tz_utc = pytz.utc

  # Create a data source for the network.
  dataSource = FileRecordStream(streamID=fq_input_filename)
  numRecords = dataSource.getDataRowCount()
  network = createNetwork(dataSource=dataSource, fq_model_filename=fq_model_filename)

  # Configure the network according to the model parameters
  configureNetwork(network=network, predicted_field=predicted_field)

  # pop one item off the top of the actuals and timestamps, so the
  # actual and predicted values will line up
  del(ACTUALS[0])
  del(TIMESTAMPS[0])
  ACTUALS.append(0.0)
  TIMESTAMPS.append(TIMESTAMPS[-1] + add_time(time_units=time_units))

  print('Saving results to "{}"'.format(fq_results_filename))
  with open(fq_results_filename, 'w+') as out_file:
    # output results file header
    header = ','.join(['Row', 'Timestamp',
              'Actual', # 'Actual Change', 'Actual Direction',
              'Prediction', # 'Predicted Change', 'Predicted Direction',
              # 'Correct', 'Score',
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
      # prediction2 = predictionResults[2]["predictedValue"]
      # prediction3 = predictionResults[3]["predictedValue"]
      # prediction4 = predictionResults[4]["predictedValue"]
      # prediction5 = predictionResults[5]["predictedValue"]
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
      # score = sum(scores) / len(scores) * 100

      # print out results
      dt_utc = tz_utc.localize(TIMESTAMPS[iteration])
      dt_local = dt_utc.astimezone(tz_local)
      row = '{}'.format(iteration + 1).rjust(row_col_len, ' ')
      msg = "Row {}:\t{}\t".format(row, dt_local)
      msg += "actual value:{:14.8f}\t".format(actual)
      msg += "predicted values:{:14.8f}\t".format(prediction)
      # msg += "{:14.8f}\t".format(prediction2)
      # msg += "{:14.8f}\t".format(prediction3)
      # msg += "{:14.8f}\t".format(prediction4)
      # msg += "{:14.8f}\t".format(prediction5)
      # msg += "{}\t".format(correct_colored)
      # msg += "score: {:.2f}%\t".format(score)
      msg += "error: {:.5f}%\t".format(avg_pct_error)
      msg += "confidence: {:.2f}%\t".format(oneStepConfidence * 100)
      print(msg)

      # Write results to output file
      msg = "{},{},".format(iteration + 1, dt_local)
      msg += "{:.8f},".format(actual)
      msg += "{:.8f},".format(prediction)
      # msg += "{:.8f},".format(prediction2)
      # msg += "{:.8f},".format(prediction3)
      # msg += "{:.8f},".format(prediction4)
      # msg += "{:.8f},".format(prediction5)
      # msg += "{},".format(correct)
      # msg += "{:.1f},".format(score)
      msg += "{:.5f},".format(avg_pct_error)
      msg += "{:.8f}".format(oneStepConfidence * 100)
      if iteration == 0:
        msg = msg.replace('          ', '')
      out_file.write(msg + '\n')

      # store values for next iteration
      last_actual = actual
      # last_prediction = prediction

      if iteration >= numRecords - 1:
        p = Prediction(
          time_predicted=tz_utc.localize(TIMESTAMPS[-1]),
          exchange=EXCHANGE,
          market=market,
          time_units=time_units,
          prediction_type=prediction_type,
          prediction=prediction,
          confidence=oneStepConfidence * 100,
          actual=actual,
          pct_error=error)
        print('\nNOTE! This is prediction {} out of {}'.format(iteration, numRecords))
        print('\tSending prediction to database: {}'.format(p))
        return p

  # copy the results file, so it can be plotted
  # shutil.copyfile(fq_results_filename, os.path.join(BASE_DIR, 'results.csv'))


def store_prediction(url, username, password, action, prediction):
  """
  Sends the prediction to the Django server

  :param url:
  :param username:
  :param password:
  :param action:
  :param prediction:
  :type prediction: Prediction
  :return:
  :raise: Exception
  """
  if action == 'add':
    prediction_url = '{}/ws/prediction/add/'.format(url)
  elif action == 'update':
    prediction_url = '{}/ws/prediction/update/'.format(url)
  else:
    raise ValueError("Bad value in 'action' parameter: {}".format(action))
  params = dict(
    action=action,
    username=username,
    password=password,
    time_predicted=prediction.time_predicted,
    exchange=prediction.exchange,
    market=prediction.market,
    time_units=prediction.time_units,
    type=prediction.prediction_type,
    prediction=prediction.prediction,
    confidence=prediction.confidence)
  r = requests.get(url=prediction_url, params=params)
  if r.status_code == 200:
    print("Prediction successfully sent to server: '{}'".format(prediction_url))
  else:
    msg = "ERROR: Prediction failed to send to server: '{}'".format(prediction_url)
    print(msg)
    raise Exception(msg)


def get_services(url, username, password):
  """
  Gets the "running" services from the Django web-service identified by the 'url'

  :param url:
  :type url: str
  :param username:
  :type username: str
  :param password:
  :type password: str
  :return: Example: {'hostname': 'codehammer.binarycapital.io', 'port': 52000, 'authkey': 'password'}
  :rtype: dict
  """
  params = {'username': username, 'password': password, 'name': 'bitmex'}
  r = requests.get(url=url, params=params)
  if r.status_code == 200:
    services = json.loads(r.content)
  else:
    raise Exception('ERROR returned by Django server ({}): {}'.format(r.status_code, r.content))

  for service in services:
    if service['hostname'] == getfqdn(gethostname()):
      return {'hostname': str(service['hostname']), 'port': service['port'], 'authkey': str(service['authkey'])}
  raise Exception('Service was not returned by the Django server')


global EXPERIMENT_NAME, INPUT_FILENAME, RESULTS_FILENAME, MODEL_FILENAME, BASE_DIR, MODEL_INPUT_FILES_DIR
global MODEL_OUTPUT_FILES_DIR, FQ_RESULTS_FILENAME, FQ_MODEL_FILENAME, FQ_MODEL_TEMPLATE_FILENAME, DATA_TABLE, MAGIC_N

# Input variables into the system
MAGIC_N = 400
EXCHANGE = 'bitmex'
NMARKET = 'XBTM18'.lower()
MARKET2 = 'XBTUSD'.lower()
DATA_TABLE = 'trade'
CURRENT_DATE_TIME = datetime.now().strftime("%Y.%m.%d.%H.%M").lower()
CURRENT_DATE = datetime.now().strftime("%Y.%m.%d").lower()
# CANDLESTICK_SIZE = '1h' # 1m = 1 minute, 5m = 5 minutes
START_DATE = datetime(2015, 10, 1, tzinfo=pytz.utc)
END_DATE = datetime(2018, 4, 1, tzinfo=pytz.utc)
DATA_POINTS = int((END_DATE - START_DATE).total_seconds() / 60 / 5) + 1

# INPUT and OUTPUT file names
EXPERIMENT_NAME = '{}.{}.{}.{}.{}'.format(CURRENT_DATE_TIME, EXCHANGE, NMARKET, DATA_TABLE, '')
INPUT_FILENAME = '{}.{}.{}.csv'.format(EXCHANGE, NMARKET, DATA_TABLE)
RESULTS_FILENAME = '{}.results.csv'.format(EXPERIMENT_NAME)
MODEL_FILENAME = '{}.model.yaml'.format(EXPERIMENT_NAME)

# INPUT and OUTPUT directory names
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_INPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_input_files')
MODEL_OUTPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_output_files/{}'.format(CURRENT_DATE))
# FQ_INPUT_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, INPUT_FILENAME)
FQ_RESULTS_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, RESULTS_FILENAME)
FQ_MODEL_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, MODEL_FILENAME)
FQ_MODEL_TEMPLATE_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, "model-one-market-quotes.yaml")

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


def get_start_end_dates(time_units):
  end = datetime.now(tz=pytz.timezone('UTC'))
  td = parse_time_units(time_units)
  start = end - td
  return { 'start':start, 'end':end }


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
    '-m' or "--markets" - a list of market symbols, delimited by a semicolon
    '-t' or "--time_units" - the time units, either: "1m", "5m", "1h", "1d"
    '-P' or "--predict" - the field name that will be predicted, e.g. "spread" or "m1_ask"

  :returns: (options, args)
  :rtype: tuple
  """

  usage = "usage: $prog [options]"
  parser = OptionParser(usage)
  df = "{}/input_data.csv".format(MODEL_INPUT_FILES_DIR)
  parser.add_option('-c', "--create", dest="create_input_file", action="store_true", default=False,
    help="create the input file from data in the database")
  parser.add_option('-f', "--file", dest="input_filename", default=df,
    help="specify the fully qualified path to a CSV filename to store input data for the model (default = {})".format(df))
  parser.add_option('-s', "--start", dest="start", default=None,
    help="the start date to get data from")
  parser.add_option('-e', "--end", dest="end", default=None,
    help="the end date to get data till")
  parser.add_option('-d', "--server", dest="server_name", default="codehammer",
    help="""the name of the Django server to get the data from (default = "codehammer")""")
  parser.add_option('-p', "--port", dest="server_port", default="80",
    help="port number the Django server is running on (default = 80)")
  parser.add_option('-m', "--market", dest="market", default="BTC/USD",
    help='a standardized market symbol (default = "BTC/USD")')
  parser.add_option('-t', "--time_units", dest="time_units", default='1m',
    help='the time units, either: "1m", "5m", "1h", "1d" (default = "1m")')
  parser.add_option('-P', "--predict", dest="predicted_field", default='btcusd_high',
    help="""'-P' or '--predict' - the field name that will be predicted, e.g. 'btcusd_high' | 'btcusd_low' (default = "btcusd_high")""")
  parser.add_option('-n', '--magic', dest='magic_number', default=400,
    help='the magic number when training will stop and predictions will begin.')
  parser.add_option('--username', dest='username', help='The user name to connect to the Django server as')
  parser.add_option('--password', dest='password', help="The Django user's password")
  parser.add_option('--topic', dest='topic', default='tradeBin1m', help="The SubPub topic to subscribe to")

  (options, args) = parser.parse_args()

  # set default start date
  if options.end is None:
    end = datetime.now(tz=pytz.timezone('UTC'))
    options.end = end

  # set default end date
  if options.start is None:
    td = parse_time_units(options.time_units)
    start = options.end - td
    options.start = start
  return options, args


if __name__ == "__main__":

  options, args = parse_options()
  create_input_file = options.create_input_file
  input_filename = options.input_filename
  MAGIC_N = int(options.magic_number)
  username = options.username
  password = options.password
  pid = os.getpid()

  # if this is a development workstation...
  if gethostname() in ['codehammer']:
    url = 'http://{}:8000'.format(gethostname())
  # if this is a production or test server...
  else:
    url = 'http://{}'.format(getfqdn(gethostname()))

  # get the Bitmex Data Server's hostname, port, and authentication key
  services_url = '{}/ws/service'.format(url)
  service = get_services(url=services_url, username=username, password=password)
  publisher_address = (service['hostname'], service['port'])

  # extract variables from the command line options
  django_server = options.server_name
  django_port = options.server_port
  market = options.market
  time_units = options.time_units
  predicted_field = options.predicted_field
  include_spread = True
  include_classification = False

  # INPUT and OUTPUT file names
  market_symbol = market.lower().replace('/', '').replace(';', '-')
  SUFFIX_NAME = 'spread-future-swap-{}'.format(time_units)
  EXPERIMENT_NAME = '{}.{}.{}.{}.{}'.format(CURRENT_DATE_TIME, EXCHANGE, market_symbol, DATA_TABLE, SUFFIX_NAME)
  INPUT_FILENAME = '{}.{}.{}.csv'.format(EXCHANGE, market_symbol, DATA_TABLE)
  RESULTS_FILENAME = '{}.results.csv'.format(EXPERIMENT_NAME)
  MODEL_FILENAME = '{}.model.yaml'.format(EXPERIMENT_NAME)

  # INPUT and OUTPUT directory names
  BASE_DIR = os.path.dirname(os.path.abspath(__file__))
  MODEL_INPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_input_files')
  MODEL_OUTPUT_FILES_DIR = os.path.join(BASE_DIR, 'model_output_files/{}'.format(CURRENT_DATE))
  FQ_RESULTS_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, RESULTS_FILENAME)
  FQ_MODEL_FILENAME = os.path.join(MODEL_OUTPUT_FILES_DIR, MODEL_FILENAME)
  FQ_MODEL_TEMPLATE_FILENAME = os.path.join(MODEL_INPUT_FILES_DIR, "model-one-market-quotes.yaml")

  # Subscriber client connection
  connection = Client(address=publisher_address, authkey=service['authkey'])
  subscription_request = {
    'action': 'subscribe',
    'hostname': getfqdn(),
    'pid': os.getpid(),
    'client': connection,
    'smarket': market,
    'topic': options.topic,
  }
  connection.send(subscription_request)
  response = connection.recv()

  if response == SUBSCRIBED:
    # the server accepted our subscription request
    print('Subscription request accepted by the Bitmex Data Server')
  elif response == INVALID_REQUEST:
    # the server rejected out subscription request
    msg = 'Subscription request was REJECTED by the Bitmex Data Server'
    print(msg)
    raise Exception(msg)

  while True:
    # wait until we receive a price update from the Bitmex Data Server (Data Manager (DM))
    try:
      data = connection.recv()
    except EOFError:
      print('The Bitmex Data Server disconnected, shutting down...')
      exit(1)

    # re-caclulate the start and end dates for the input data file
    start = get_start_end_dates(time_units=time_units)['start']
    end = get_start_end_dates(time_units=time_units)['end']

    # create the 'model_output_files' directory and copy the model template
    # file into the 'model_output_files' directory and rename it
    create_output_directory(fq_model_template_filename=FQ_MODEL_TEMPLATE_FILENAME,
                            fq_model_filename=FQ_MODEL_FILENAME,
                            model_output_files_dir=MODEL_OUTPUT_FILES_DIR)

    # if the input data file does not exist, get the data from
    # the Django server and cache it in a local CSV file in
    # the 'model_input_files' directory
    if create_input_file:
      market_data = fetch_market_data(exchange=EXCHANGE, markets=[market],
                                      data_table=DATA_TABLE, time_units=time_units,
                                      start=start, end=end,
                                      host=django_server, port=django_port)
      initialize_csv(input_filename, [market],
                     include_spread=include_spread, include_classification=include_classification)
      write_input_file(input_filename, [market], market_data, spread_as_pct=True,
                       include_spread=include_spread, include_classification=include_classification)

    # read the input data file into local variables, so the
    # nupic predictor can use them to make its predictions
    if file_exists(input_filename):
      read_input_file(fq_input_filename=input_filename)
    else:
      raise ValueError("Filename '{}' does not exist".format(input_filename))

    # run the Nupic predictor, make the predictions, and
    # save the results to the 'model_output_files' directory
    prediction = run_the_predictor(fq_input_filename=input_filename,
                      fq_model_filename=FQ_MODEL_FILENAME,
                      fq_results_filename=FQ_RESULTS_FILENAME,
                      predicted_field=predicted_field, market=market, prediction_type='H', time_units=time_units)

    # modify the permissions of the files in the output directory
    # so that everyone can read them
    modify_output_file_permissions(MODEL_OUTPUT_FILES_DIR)

    # send the prediction to the Django server
    store_prediction(url=url, username=username, password=password, action='add', prediction=prediction)














