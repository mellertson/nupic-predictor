#!/usr/bin/env python
import re
import json
import os, errno, shutil, logging
import sys
import yaml
import requests
import pandas as pd
import pytz
import traceback
import random, copy
from subprocess import Popen
from dateutil import parser, tz
from datetime import datetime, timedelta
from nupic.engine import Network
from nupic.encoders import MultiEncoder
from nupic.data.file_record_stream import FileRecordStream
from optparse import OptionParser
from nupredictor.functions import get_files
from nupredictor.utilities import parse_time_units
from socket import getfqdn, gethostname
from flask import Flask, request
import threading as t
import multiprocessing as mp


__all__ = [
	# global functions
	'bcolors',
	'calculate_start_date',
	'fetch_market_data',
	'get_file_permissions',
	'get_start_dates',
	'initialize_csv',
	'modify_output_file_permissions',
	'write_input_file',
	'get_services',
	'getPredictionResults',
	'enableLearning',
	'disableLearning',

	# classes
	'Prediction',
	'DateTimeUtils',
	'JSONMessage',
	'NupicPredictor',
	'NupicPredictorv2',

	# json functions
	'json_load_byteified',
	'json_loads_byteified',
]


app = Flask('nupic_predictor')
SUBSCRIBED = 1
UNSUBSCRIBED = 2
INVALID_REQUEST = 400


# logger settings
log = app.logger


if os.environ.get('DEBUG', True):
	keys = sorted(os.environ.keys())
	for k in keys:
		v = os.environ[k]
		log.debug('{}={}'.format(k, v))


def json_load_byteified(file_handle):
	return _byteify(
		json.load(file_handle, object_hook=_byteify),
		ignore_dicts=True
	)

def json_loads_byteified(json_text):
	return _byteify(
		json.loads(json_text, object_hook=_byteify),
		ignore_dicts=True
	)

def _byteify(data, ignore_dicts=False):
	# if this is a unicode string, return its string representation
	if isinstance(data, unicode):
		return data.encode('utf-8')
	# if this is a list of values, return list of byteified values
	if isinstance(data, list):
		return [_byteify(item, ignore_dicts=True) for item in data]
	# if this is a dictionary, return dictionary of byteified keys and values
	# but only if we haven't already byteified it
	if isinstance(data, dict) and not ignore_dicts:
		return {
			_byteify(key, ignore_dicts=True): _byteify(value, ignore_dicts=True)
			for key, value in data.iteritems()
		}
	# if it's anything else, return it in its original form
	return data

def error_log_stack(e):
	"""
	Outputs the curret stack trace and the exception's text to the root error logger

	:param e:
	:type e: Exception
	"""

	# ss = traceback.extract_tb(sys.exc_info()[2])
	# stack = traceback.format_list(ss)
	# log.error(stack)
	# log.error('Exception: {}'.format(e))
	# for line in stack:
	# 	sys.stderr.writelines(line + '\n')
	# sys.stderr.writelines([''])
	# sys.stderr.writelines(['Exception: {}'.format(e)])
	log.error(e, exc_info=True)


class StopThread(Exception):
	""" Raised to stop the current thread """


class DateTimeUtils(object):
	FMT = "%m/%d/%Y %I:%M %P (%Z)"
	utc_zone = tz.tzutc()
	local_zone = tz.tzlocal()
	ptn = re.compile(r'(?P<value>[\d]+)(?P<units>[smhd])')

	@classmethod
	def timedelta_to_units_and_value(cls, td):
		"""
		Transform a timedelta object into its "units" (e.g. minutes, hours, or days) and "value" (e.g. 30, 24, or 1)

		:param td:
		:type td: timedelta

		:return: (str, int)
		:rtype: tuple
		"""

		mm, ss = divmod(td.total_seconds(), 60)
		hh, mm = divmod(mm, 60)
		if mm > 0:
			return 'm', int(mm)
		elif hh > 0:
			if hh == 24:
				return 'd', 1
			else:
				return 'h', int(hh)
		else:
			return 'd', int(td.days)

	@classmethod
	def string_to_timeframe(cls, timeframe):
		"""
		Transform a string into a timedelta object

		:param timeframe:
			Choices are: '15s' | '15m' | '30m' | '1m' | '5m' | '1h' | '1d'
		:type timeframe: str

		:return:
			A timedelta equivilent to the 'timeframe' argument
		:rtype: timedelta
		"""
		msg = 'Invalid "timeframe" parameter: {}'.format(timeframe)
		m = cls.ptn.search(timeframe)
		if m:
			value = int(m.group('value'))
			units = m.group('units')
			if units == 's':
				return timedelta(seconds=value)
			elif units == 'm':
				return timedelta(minutes=value)
			elif units == 'h':
				return timedelta(hours=value)
			elif units == 'd':
				return timedelta(days=value)
			else:
				raise ValueError(msg)
		else:
			raise ValueError(msg)

	@classmethod
	def format_usa(cls, dt):
		return dt.strftime(cls.FMT)


class Prediction(dict):
	def __init__(self, time_predicted, exchange, market, timeframe,
				 prediction_type, prediction, confidence, actual, pct_error, anomaly_score,
				 predicted_field=None):
		super(Prediction, self).__init__()
		log.debug('Constructing a prediction:')
		log.debug('\ttime_predicted: {}'.format(time_predicted))
		log.debug('\texchange: {}'.format(exchange))
		log.debug('\tmarket: {}'.format(market))
		log.debug('\ttimeframe: {}'.format(timeframe))
		log.debug('\tprediction_type: {}'.format(prediction_type))
		log.debug('\tprediction: {}'.format(prediction))
		log.debug('\tconfidence: {}'.format(confidence))
		log.debug('\tactual: {}'.format(actual))
		log.debug('\tpct_error: {}'.format(pct_error))
		log.debug('\tanomaly_score: {}'.format(anomaly_score))
		log.debug('\tpredicted_field: {}'.format(predicted_field))

		self['time_predicted'] = str(time_predicted)
		self['exchange'] = str(exchange)
		self['market'] = str(market)
		self['timeframe'] = str(timeframe)
		self['prediction_type'] = str(prediction_type)
		self['prediction'] = float(prediction)
		self['confidence'] = float(confidence)
		self['actual'] = float(actual)
		self['pct_error'] = float(pct_error) if pct_error else 0.0
		self['anomaly_score'] = float(anomaly_score)
		self['predicted_field'] = predicted_field


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


def create_output_directory(fq_model_template_filename, fq_model_filename,
							model_output_files_dir):
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


def fetch_market_data(exchange, markets, data_table, start, end, timeframe,
					  username='test_user', password='test', host='localhost', port=8000,
					  protocol='http'):
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
	:param timeframe: '1m' | '5m' | '1h' | '1d'
	:type timeframe: str
	:param username:
	:type username: str
	:param password:
	:type password: str
	:param host:
	:type host: str
	:param port:
	:type port: int
	:param protocol: 'http' | 'https'
	:type protocol: str

	:return: Pandas DataFrames, e.g.: {'BTC/USD': dataframe, 'BTC/M18': dataframe}
	:rtype: dict
	"""

	# local variables
	base_url = '{}://{}:{}/data/get/{}'.format(protocol, host, port, data_table.lower())
	frames = {}

	# for each market...
	for market in markets:
		# build the input variables needed by the web-service
		params1 = {'username':   username, 'passwd': password, 'exchange': exchange, 'symbol': market,
				   'data_table': data_table, 'start': start.isoformat(), 'end': end.isoformat(),
				   'timeframe': timeframe}

		# send the HTTP request and decode the JSON response
		log.debug('Getting data from: ' + base_url)
		response = requests.get(base_url, params=params1, timeout=60*60)
		if response.status_code != 200:
			raise ValueError('No {}-{} data was found between {} and {} for {}'
							 .format(exchange, market, start, end, timeframe))
		data = pd.read_json(response.content, orient='record', precise_float=True)

		# verify there is at least 1 row of data in each data set
		if len(data) < 1:
			raise ValueError('No {}-{} data was found between {} and {} for {}'
							 .format(exchange, market, start, end, timeframe))

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


def initialize_csv(fq_input_filename, markets,
				   include_spread=True, include_classification=False):
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


def createSensorToClassifierLinks(network, sensorRegionName, classifierRegionName):
	"""Create required links from a sensor region to a classifier region."""
	network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
				 srcOutput="bucketIdxOut", destInput="bucketIdxIn")
	network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
				 srcOutput="actValueOut", destInput="actValueIn")
	network.link(sensorRegionName, classifierRegionName, "UniformLink", "",
				 srcOutput="categoryOut", destInput="categoryIn")


def createEncoder(encoderParams):
	"""Create a multi-encoder from params."""
	log.debug('creating encoders using encoder params: {}'.format(encoderParams))
	encoder = MultiEncoder()
	encoder.addMultipleEncoders(encoderParams)
	return encoder


def getPredictionResults(network, clRegionName):
	"""
	Get all multi-step predictions from a Nupic region.

	:rtype: list of dict
	"""
	classifierRegion = network.regions[clRegionName]
	temporalPoolerRegion = network.regions["TM"]
	sensorRegion = network.regions["sensor"]
	input_value = sensorRegion.getOutputData("sourceOut")[1]
	actualValues = classifierRegion.getOutputData("actualValues")
	probabilities = classifierRegion.getOutputData("probabilities")
	anomalyScore = temporalPoolerRegion.getOutputData("anomalyScore")[0]

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
		results[steps[i]]["inputValue"] = input_value
		results[steps[i]]["anomalyScore"] = anomalyScore
	return results


def enableLearning(network, model_params):
	""" Enable learning for all regions in a Nupic network. """
	network.regions["SP"].setParameter("learningMode", True)
	network.regions["TM"].setParameter("learningMode", True)
	for regionName, region in model_params['classifiers'].items():
		network.regions[regionName].setParameter('learningMode', True)


def disableLearning(network, model_params):
	""" Disable learning for all regions in a Nupic network. """
	network.regions["SP"].setParameter("learningMode", False)
	network.regions["TM"].setParameter("learningMode", False)
	for regionName, region in model_params['classifiers'].items():
		network.regions[regionName].setParameter('learningMode', False)


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
		time_units=prediction.timeframe,
		type=prediction.prediction_type,
		prediction=prediction.prediction,
		confidence=prediction.confidence)
	r = requests.get(url=prediction_url, params=params)


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


def get_start_end_dates(time_units):
	end = datetime.now(tz=pytz.timezone('UTC'))
	td = parse_time_units(time_units)
	start = end - td
	return { 'start':start, 'end':end }


def constructor(loader, node):
	return node.value


class JSONMessage(object):
	TYPE_HEADER = 'header-row'
	TYPE_NET_INITIALIZED = 'network-initialized'
	TYPE_PREDICT = 'predict'
	TYPE_PREDICT_N_LEARN = 'predict-and-learn'
	TYPE_PREDICTION_RESULT = 'prediction-result'
	TYPE_TRAIN_NUPIC = 'train-Nupic'
	TYPE_TRAIN_CONFIRMATION = 'training-confirmation'
	TYPE_QUIT = 'quit'

	@classmethod
	def build(cls, message_type, message):
		"""
		Build a JSON message from a message in a Python dictionary

		:param message_type:
			Either: 'header-row', 'network-initialized', 'prediction', 'training-confirmation'
		:type message_type: str
		:param message:
		:type message: dict | str
		:return:
			A message with the following format:
				{
					'type': 'header-row' | 'network-initialized' | 'prediction' | 'training-confirmation',
					'message': message,
				}
		:rtype: dict
		"""
		return {'type': message_type, 'message': message}


class NupicPredictor(t.Thread):
	"""
	A predictor which constructs and uses a Nupic model

	:ivar network:
		The Nupic network (the model)
	:type network: nupic.engine.Network
	:ivar predicted_field:
			The "fieldname", identified in the model parameters file,
			which will be predicted, e.g. "spread" or "m1_ask"
	:type predicted_field: str
	"""

	def __init__(self, topic='trade', exchange='bittrex', market='btc/usd',
				 predicted_field=None, timeframe='1m',
				 parse_args=False, model_filename=None, model_identity=None):
		super(NupicPredictorv2, self).__init__(
			target=self.run, name='NupicPredictor.run')
		self.network = None
		self.model_identity = model_identity
		if parse_args:
			self.options = self.parse_options()[0]
			self.options.exchange = exchange
			self.options.market = market
			self.options.timeframe = timeframe
		else:
			self.options = self
			self.options.exchange = exchange
			self.options.market = market
			self.options.predicted_field = predicted_field
			self.options.timeframe = timeframe
			self.options.model = model_filename
		self.models_dir = 'model_input_files'
		if self.options.model:
			self.model_filename = self.options.model
		else:
			self.model_filename = 'nupic_predict_buys_sells_model.yaml'
		self.dir = os.path.join(
			self.models_dir,
			os.path.dirname(os.path.abspath(__file__)))
		self.model_fqfn = os.path.join(
			os.path.join(self.dir, 'model_input_files'),
			self.model_filename)
		self.results_fqfn = self.build_dir('results.csv')
		self.exchange_id = self.options.exchange
		self.symbol = self.options.market
		self.symbol_fixed = self.options.market.replace('/', '')
		self.predicted_field = self.options.predicted_field
		self.timeframe = self.options.timeframe
		self.timeframe_td = DateTimeUtils.string_to_timeframe(self.timeframe)
		self.input_filename = '/tmp/{}-{}.csv'.format(
			self.name, random.randint(1, 999999999))
		self.input_file = open(self.input_filename, 'w+')
		self.is_started = t.Event()
		self.is_started.clear()
		self.command_queue = mp.Queue()
		self.output_msg_queue = mp.Queue()
		log.debug('Nupic Predictor initialized')
		log.debug('-' * 100)

	def __del__(self):
		if not self.input_file.closed:
			self.input_file.close()
		log.debug('Input file closed: {}'.format(self.input_filename))
		Popen(['rm', '{}'.format(self.input_filename)])

	def __str__(self):
		return self.name

	def __repr__(self):
		return self.__str__()

	@property
	def name(self):
		return 'nunetwork'

	def build_dir(self, filename):
		return os.path.join(self.dir, filename)

	def parse_options(self):
		"""
		Parse command line options and return them

		:returns: (options, args)
		:rtype: tuple
		"""

		usage = "usage: nunetwork.py [options]\n\n"
		parser = OptionParser(usage)

		parser.add_option('-P', "--predicted-field", dest="predicted_field",
			help="""The fieldname, which should be predicted.""")
		parser.add_option('--model', dest='model',
			help="""The Nupic model filename (must be fully qualified).""")

		(options, args) = parser.parse_args()
		return options, args

	def create_network(self, data_source):
		"""
		Create and initialize the Nupic network (a.k.a. model)

		:param data_source: The input data source for the Nupic model
		:type data_source: FileRecordStream

		:returns: A fully initialized Nupic network (a.k.a. model)
		:rtype: nupic.engine.Network
		"""

		with open(self.model_fqfn, "r") as f:
			modelParams = yaml.safe_load(f)["modelParams"]

		# Create a network that will hold the regions
		network = Network()

		################################################################################
		# Add sensor regions
		################################################################################
		network.addRegion("sensor", "py.RecordSensor", '{}')

		# Set the encoder and data source of the sensor region.
		sensorRegion = network.regions["sensor"].getSelf()
		sensorRegion.encoder = createEncoder(modelParams["sensorParams"]["encoders"])
		sensorRegion.dataSource = data_source

		################################################################################
		# Synchronize Sensor Region output width with Spatial Pooler input width
		################################################################################
		modelParams["spParams"]["inputWidth"] = sensorRegion.encoder.getWidth()

		################################################################################
		# Add SP and TM regions
		################################################################################
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
		network.initialize()

		return network

	def configure_network(self, network):
		"""
		Configure the Nupic network

		Does the following:
		  - sets the "predicted field" found in the data source
		  - turns on "learning mode" for all regions in the network
		  - turns on "inference mode" for all regions in the network

		:param network:
			A fully initialized Nupic network (a.k.a. the model)
		:type network: Network

		:rtype: nupic.engine.Network
		"""

		# Set predicted field
		network.regions["sensor"].setParameter(
			"predictedField",
			self.predicted_field)

		# Enable learning for all regions
		network.regions["SP"].setParameter("learningMode", True)
		network.regions["TM"].setParameter("learningMode", True)
		network.regions["classifier"].setParameter("learningMode", True)

		# Enable inference for all regions
		network.regions["SP"].setParameter("inferenceMode", True)
		network.regions["TM"].setParameter("inferenceMode", True)
		network.regions["classifier"].setParameter("inferenceMode", True)

		# We want temporal anomalies so disable anomalyMode in the SP. This mode is
		# used for computing anomalies in a non-temporal model.
		network.regions["SP"].setParameter("anomalyMode", False)

		# Enable topDownMode to get the predicted columns output
		network.regions["TM"].setParameter("topDownMode", True)

		# Enable anomalyMode to compute the anomaly score.
		network.regions["TM"].setParameter("anomalyMode", True)

		return network

	def write_to_input_file(self, data, append_newline=True):
		"""
		Write the given data string to the Nupic model's input file

		:param data:
			The data to be written to the Nupic model's input file
		:type data: string
		:param append_newline:
			If True, a newline will be written to the input file
		:type append_newline: bool

		:rtype: None
		"""

		self.input_file.write(data)
		if append_newline:
			self.input_file.write('\n')
		self.input_file.flush()

	def get_next_data(self):
		"""
		Read JSON from standard input as next data point

		:rtype:  dict
		"""

		try:
			# block until the next trade or command is recieved
			json_data = sys.stdin.readline()
			log.debug('data read from stdin: {}'.format(json_data))
			if len(json_data) > 0:
				data = json.loads(json_data)
				return data
			return {}
		except ValueError as e:
			log.error(str(e))
		except EOFError:
			exit(1)

	def get_next_prediction(self, network, data):
		"""
		Make a prediction and save it to the 'model_output_files' directory

		:param network:
			The Nupic network, which will make the prediction
		:type network: nupic.engine.Network
		:param data:
		:type data: dict

		:rtype: Prediction
		"""

		# make one prediction
		network.run(1)

		# extract the prediction
		predictionResults = getPredictionResults(network, "classifier")
		predicted_value = predictionResults[1]["predictedValue"]
		confidence = predictionResults[1]["predictionConfidence"]
		tc = parser.parse(data['message']['timestamp'])
		tp = tc + self.timeframe_td
		p = Prediction(
			time_predicted=str(tp),
			exchange=self.exchange_id,
			market=self.symbol,
			timeframe=self.timeframe,
			prediction_type='F',
			prediction=predicted_value,
			confidence=confidence * 100,
			actual=predictionResults[1]['inputValue'],
			pct_error=None,
			anomaly_score=predictionResults[1]['anomalyScore'],
		)
		return p

	def train(self, network):
		"""
		Train the network without making a prediction

		:param network:
			The Nupic network, which will be trained
		:type network: nupic.engine.Network

		:rtype: None
		"""

		network.run(1)

	def output_prediction(self, prediction):
		"""
		Write the prediction to standard output as a JSON string

		:param prediction:
			The prediction to write to standard output
		:type prediction: Prediction
		:return:
			The JSON string which was written to standard output
		:rtype: str
		"""

		prediction['predicted_field'] = self.predicted_field
		prediction_message = JSONMessage.build(
			JSONMessage.TYPE_PREDICTION_RESULT,
			prediction)
		return self.output_message(prediction_message)

	def output_training_confirmation(self):
		"""
		Write a confirmation message to standard output as a JSON string

		:return:
			A confirmation message as a JSON string
		:rtype: str
		"""

		confirmation = JSONMessage.build(
			JSONMessage.TYPE_TRAIN_CONFIRMATION,
			'The Nupic network was trained successfully')
		return self.output_message(confirmation)

	def output_message(self, message):
		"""
		Write a message to standard output as a JSON string

		:param message:
			A Python dictionary which will be converted to a
			JSON string and written to standard output
		:type message: dict

		:rtype: str
		"""
		self.output_message.put(message)
		json_string = json.dumps(message)
		log.debug('data written to stdout: {}'.format(json_string))
		sys.stdout.write(json_string)
		sys.stdout.write('\n')
		sys.stdout.flush()
		return json_string

	def predictor_thread(self):
		self.network = None
		while True:
			# block until the next command is
			# received on standard input
			data = self.get_next_data()

			if 'type' in data:
				# instantiate and initialize the Nupic network
				if data['type'] == JSONMessage.TYPE_HEADER:
					for key, line in data['message'].items():
						self.write_to_input_file(line)

					data_source = FileRecordStream(self.input_filename)
					self.network = self.create_network(data_source)
					self.network = self.configure_network(self.network)
					self.output_message(JSONMessage.build(
						JSONMessage.TYPE_NET_INITIALIZED,
						'The Nupic network was successfully initialized')
					)

				# make a prediction
				elif data['type'] in ['predict-and-learn', JSONMessage.TYPE_PREDICT]:
					self.write_to_input_file(data['message']['row'])

					# turn on learning
					if data['type'] == 'predict-and-learn':
						enableLearning(self.network)

					# turn off learning
					elif data['type'] == JSONMessage.TYPE_PREDICT:
						disableLearning(self.network)

					# make and return the prediction
					p = self.get_next_prediction(self.network, data)
					log.debug('Nupic made prediction = {}'.format(p))
					self.output_prediction(p)

				# just train the network
				elif data['type'] == JSONMessage.TYPE_TRAIN_NUPIC:
					log.debug('Training Nupic with: {}'.format(data['message']['row']))
					self.write_to_input_file(data['message']['row'])
					enableLearning(self.network)
					self.train(self.network)
					self.output_training_confirmation()

				# write "raw" data to input file without a
				# newline character and make a prediction
				elif data['type'] == 'raw':
					self.write_to_input_file(data['row'], append_newline=False)
					p = Prediction(
						time_predicted=str(datetime.now(tz=pytz.UTC)),
						exchange=self.exchange_id,
						market=self.symbol,
						timeframe=self.timeframe,
						prediction_type='F',
						prediction=1000.0,
						confidence=1.0,
						actual=None,
						pct_error=0.0,
						anomaly_score=None)
					self.output_prediction(p)

				# shut down the predictor
				elif data['type'] == JSONMessage.TYPE_QUIT:
					exit(0)
			else:
				log.error('''"type" key not found in data''')
				log.error('''---> data = {}'''.format(data))
				exit(1)

	def run(self):
		"""
		The main entry point of this nupic predictor

		:rtype: None
		"""

		try:
			self.is_started.set()
			self.predictor_thread()
		except KeyboardInterrupt as e:
			self.input_file.close()
			raise e
		except StopIteration as e:
			error_log_stack(e)
			raise e
		except Exception as e:
			error_log_stack(e)
			raise e

	def desired_output(self, x, r, l=0.0, m=0.5, h=1.0):
		if x < m:
			s = abs(m - l)
			o = l + s * r
			y = o
		else:
			s = abs(h - m)
			o = m + s * r
			y = o
		return y


class NupicPredictorv2(t.Thread):
	"""
	A predictor which constructs and uses a Nupic model

	:ivar network:
		The Nupic network (the model)
	:type network: nupic.engine.Network
	:ivar predicted_field:
			The "fieldname", identified in the model parameters file,
			which will be predicted, e.g. "spread" or "m1_ask"
	:type predicted_field: str
	"""

	def __init__(self, exchange='bittrex', market='btc/usd',
				 predicted_field=None, timeframe='1m',
				 parse_args=False, model_filename=None, model_identity=None):
		super(NupicPredictorv2, self).__init__(
			target=self.run, name='NupicPredictor.run')
		self.network = None
		self.model_identity = model_identity
		if parse_args:
			self.options = self.parse_options()[0]
			self.options.exchange = exchange
			self.options.market = market
			self.options.timeframe = timeframe
		else:
			self.options = self
			self.options.exchange = exchange
			self.options.market = market
			self.options.predicted_field = predicted_field
			self.options.timeframe = timeframe
			self.options.model = model_filename
		self.models_dir = 'model_input_files'
		if self.options.model:
			self.model_filename = self.options.model
		else:
			self.model_filename = 'nupic_predict_buys_sells_model.yaml'
		self.dir = os.environ.get('NUPIC_MODEL_DIR')
		self.model_fqfn = os.path.join(
			os.path.join(self.dir, 'model_input_files'),
			self.model_filename)
		self.results_fqfn = self.build_dir('results.csv')
		self.exchange_id = self.options.exchange
		self.symbol = self.options.market
		self.symbol_fixed = self.options.market.replace('/', '')
		self.predicted_field = self.options.predicted_field
		self.timeframe = timeframe
		self.timeframe_td = DateTimeUtils.string_to_timeframe(self.timeframe)
		log.debug('{}.timeframe = {}'.format(self.__class__.__name__, self.timeframe))
		log.debug('{}.timeframe_td = {}'.format(self.__class__.__name__, self.timeframe_td))
		self.input_filename = '/tmp/{}-{}.csv'.format(
			self.name, random.randint(1, 999999999))
		self.input_file = open(self.input_filename, 'w+')
		self.is_started = t.Event()
		self.is_started.clear()
		self.command_queue = mp.Queue()
		self.output_msg_queue = mp.Queue()
		log.debug('Nupic Predictor initialized')
		log.debug('-' * 100)
		self.model_params = {}
		self.state_lock = t.Lock()
		self._state = 'stopped'

	def __del__(self):
		if not self.input_file.closed:
			self.input_file.close()
		log.debug('Input file closed: {}'.format(self.input_filename))
		Popen(['rm', '{}'.format(self.input_filename)])

	def __str__(self):
		return self.model_identity

	def __repr__(self):
		return 'NupicPredictorV2({})'.format(self.model_identity)

	@property
	def state(self):
		_state = None
		self.state_lock.acquire()
		_state = copy.deepcopy(self._state)
		self.state_lock.release()
		return _state

	@state.setter
	def state(self, new_state):
		self.state_lock.acquire()
		self._state = copy.deepcopy(new_state)
		self.state_lock.release()
		return new_state

	@property
	def model_name(self):
		return '{}({})'.format(
			self.__class__.__name__,
			self.model_identity,
		)

	@property
	def is_running(self):
		if self.state == 'stopped':
			return False
		else:
			return True

	def build_dir(self, filename):
		return os.path.join(self.dir, filename)

	def parse_options(self):
		"""
		Parse command line options and return them

		:returns: (options, args)
		:rtype: tuple
		"""

		usage = "usage: nunetwork.py [options]\n\n"
		parser = OptionParser(usage)

		parser.add_option('-P', "--predicted-field", dest="predicted_field",
			help="""The fieldname, which should be predicted.""")
		parser.add_option('--model', dest='model',
			help="""The Nupic model filename (must be fully qualified).""")

		(options, args) = parser.parse_args()
		return options, args

	def create_network(self, data_source):
		"""
		Create and initialize the Nupic network (a.k.a. model)

		:param data_source: The input data source for the Nupic model
		:type data_source: FileRecordStream

		:returns: A fully initialized Nupic network (a.k.a. model)
		:rtype: nupic.engine.Network
		"""

		log.debug('opening Nupic model file: {}'.format(self.model_fqfn))
		with open(self.model_fqfn, "r") as f:
			# yaml.SafeLoader.add_constructor("tag:yaml.org,2002:python/unicode", constructor)
			modelParams = yaml.safe_load(f)
			log.debug('loading Nupic model from YAML file: {}'.format(modelParams))
			modelParams = modelParams["modelParams"]
			log.debug('Nupic model params loaded: {}'.format(modelParams))
			self.model_params = modelParams

		# Create a network that will hold the regions
		network = Network()

		################################################################################
		# Add sensor regions
		################################################################################
		# Set the encoder and data source of the sensor region.
		log.debug('adding "sensor" region to Nupic network')
		sensorRegion = network.addRegion("sensor", "py.RecordSensor", '{}')
		sensorRegion.getSelf().encoder = createEncoder(modelParams["sensorParams"]["encoders"])
		sensorRegion.getSelf().dataSource = data_source

		################################################################################
		# Synchronize Sensor Region output width with Spatial Pooler input width
		################################################################################
		log.debug('synchronizing input width to Nupic model')
		modelParams["spParams"]["inputWidth"] = sensorRegion.getSelf().encoder.getWidth()

		################################################################################
		# Add SpacialPooling and TemporalMemory regions
		################################################################################
		network.addRegion("SP", "py.SPRegion", json.dumps(modelParams["spParams"]))
		network.addRegion("TM", "py.TMRegion", json.dumps(modelParams["tmParams"]))

		################################################################################
		# Classifier Regions
		################################################################################
		for regionName, region in modelParams['classifiers'].items():
			log.debug('adding classifier region({}) with classifier params: {}'.format(
				regionName, region
			))
			# Add the classifier region
			regionType = "py.%s" % region.pop("regionType")
			network.addRegion(regionName, regionType, json.dumps(region))

		################################################################################
		# Link the Regions
		################################################################################
		for regionName, region in modelParams['classifiers'].items():
			createSensorToClassifierLinks(network, "sensor", regionName)
		createDataOutLink(network, "sensor", "SP")
		createFeedForwardLink(network, "SP", "TM")
		for regionName, region in modelParams['classifiers'].items():
			createFeedForwardLink(network, "TM", regionName)
		# Reset links are optional, since the sensor region does not send resets
		createResetLink(network, "sensor", "SP")
		createResetLink(network, "sensor", "TM")

		################################################################################
		# Initialize the Network
		################################################################################
		network.initialize()

		return network

	def post_initialization(self, network):
		"""
		Do post initialization of the Nupic network with learning disabled.

		Does the following:
		  - sets the "predicted field" found in the data source
		  - turns off "learning mode" for all regions in the network
		  - turns on "inference mode" for all regions in the network

		:param network:
			A fully initialized Nupic network (a.k.a. the model)
		:type network: nupic.engine.Network

		:rtype: nupic.engine.Network
		"""

		# Set predicted field
		network.regions["sensor"].setParameter(
			"predictedField",
			self.predicted_field)

		# Disable learning for all regions
		network.regions["SP"].setParameter("learningMode", False)
		network.regions["TM"].setParameter("learningMode", False)
		for regionName, region in self.model_params['classifiers'].items():
			network.regions[regionName].setParameter('learningMode', False)

		# Enable inference for all regions
		network.regions["SP"].setParameter("inferenceMode", True)
		network.regions["TM"].setParameter("inferenceMode", True)
		for regionName, region in self.model_params['classifiers'].items():
			network.regions[regionName].setParameter("inferenceMode", True)

		# We want temporal anomalies so disable anomalyMode in the SP. This mode is
		# used for computing anomalies in a non-temporal model.
		network.regions["SP"].setParameter("anomalyMode", False)

		# Enable topDownMode to get the predicted columns output
		network.regions["TM"].setParameter("topDownMode", True)

		# Enable anomalyMode to compute the anomaly score.
		network.regions["TM"].setParameter("anomalyMode", True)

		return network

	def write_to_input_file(self, data, append_newline=True):
		"""
		Write the given data string to the Nupic model's input file

		:param data: The data to be written to the Nupic model's input file
		:type data: string
		:param append_newline: If True, a newline will be written to the
			input file
		:type append_newline: bool

		:rtype: None
		"""
		self.input_file.write(data)
		if append_newline:
			self.input_file.write('\n')
		self.input_file.flush()

	def await_input_data_from_file(self):
		"""
		Block until read JSON from standard input as next data point completes.

		:rtype:  dict
		"""

		try:
			# block until the next trade or command is recieved
			json_data = sys.stdin.readline()
			log.debug('data read from stdin: {}'.format(json_data))
			if len(json_data) > 0:
				data = json.loads(json_data)
				return data
			return {}
		except ValueError as e:
			log.error(str(e))
		except EOFError:
			exit(1)

	def await_input_data_from_command_queue(self):
		"""
		Block until data is popped from the command queue.

		:rtype:  dict
		"""
		from Queue import Empty
		while self.is_running:
			try:
				# block until the next trade or command is recieved
				data = self.command_queue.get(timeout=1.0)
				log.debug('data read from command queue: {}'.format(data))
				if len(data) > 0:
					return data
				return {}
			except Empty:
				continue
			except ValueError as e:
				log.error(str(e))
			except EOFError:
				self.state = 'stopped'

	def get_prediction(self, network, data, regionName):
		"""
		Make a prediction and save it to the 'model_output_files' directory

		:param network:
			The Nupic network, which will make the prediction
		:type network: nupic.engine.Network
		:param data:
		:type data: dict
		:param regionName: The named region to get the prediction for.
		:type regionName: str

		:rtype: Prediction
		"""

		# extract the prediction
		predictionResults = getPredictionResults(network, regionName)
		predicted_value = predictionResults[1]["predictedValue"]
		confidence = predictionResults[1]["predictionConfidence"]
		log.debug('data = {}'.format(data))
		tc = parser.parse(data['data'].split(',')[0])
		tp = tc + self.timeframe_td
		p = Prediction(
			time_predicted=str(tp),
			exchange=self.exchange_id,
			market=self.symbol,
			timeframe=self.timeframe,
			prediction_type='F',
			prediction=predicted_value,
			confidence=confidence * 100,
			actual=predictionResults[1]['inputValue'],
			pct_error=None,
			anomaly_score=predictionResults[1]['anomalyScore'],
			predicted_field=self.predicted_field,
		)
		return p

	def train(self, network):
		"""
		Train the network without making a prediction

		:param network:
			The Nupic network, which will be trained
		:type network: nupic.engine.Network

		:rtype: None
		"""

		network.run(1)

	def build_prediction_msg(self, predictions):
		"""
		Build a prediction messages from a prediction object.

		:param predictions: The prediction.
		:type predictions: list of Prediction
		:return: A prediction message.
		:rtype: dict
		"""
		for p in predictions:
			p['predicted_field'] = self.predicted_field
		prediction_message = {
			'type': JSONMessage.TYPE_PREDICTION_RESULT,
			'message': predictions,
		}
		return prediction_message

	def output_training_confirmation(self):
		"""
		Write a confirmation message to standard output as a JSON string

		:return:
			A confirmation message as a JSON string
		:rtype: str
		"""

		confirmation = JSONMessage.build(
			JSONMessage.TYPE_TRAIN_CONFIRMATION,
			'The Nupic network was trained successfully')
		return self.output_message_to_stdout(confirmation)

	def output_message_to_stdout(self, message):
		"""
		Write a message to standard output as a JSON string

		:param message:
			A Python dictionary which will be converted to a
			JSON string and written to standard output
		:type message: dict

		:rtype: str
		"""

		json_string = json.dumps(message)
		log.debug('data written to stdout: {}'.format(json_string))
		sys.stdout.write(json_string)
		sys.stdout.write('\n')
		sys.stdout.flush()
		return json_string

	def enable_learning(self):
		enableLearning(self.network, self.model_params)

	def disable_learning(self):
		disableLearning(self.network, self.model_params)

	def predictor_thread(self):
		self.network = None
		while self.is_running:
			# block until the next command is
			# received on standard input
			msg = self.await_input_data_from_command_queue()

			if msg and 'type' in msg:
				# instantiate and initialize the Nupic network
				if msg['type'] == JSONMessage.TYPE_HEADER:
					for line in msg['data']:
						self.write_to_input_file(line)
						log.info('Nupic received header data: {}'.format(line))

					try:
						data_source = FileRecordStream(self.input_filename)
						self.network = self.create_network(data_source)
						self.network = self.post_initialization(self.network)
						self.output_msg_queue.put({
							'message': '{} initialized.'.format(self.model_name),
						})
					except Exception as e:
						log.error(str(e), exc_info=True)
						raise e
					log.info('{} was initialized'.format(self.__repr__()))

				# make a prediction
				elif msg['type'] == JSONMessage.TYPE_PREDICT:
					self.write_to_input_file(msg['data'])
					self.network.run(1)

					# make and return the prediction
					predictions = []
					for regionName in self.model_params['classifiers'].keys():
						p = self.get_prediction(self.network, msg, regionName)
						predictions.append(p)
						log.debug('Nupic made prediction = {}'.format(p))
					msg = self.build_prediction_msg(predictions)
					self.output_msg_queue.put(msg)

				# shut down the predictor
				elif msg['type'] == JSONMessage.TYPE_QUIT:
					self.state = 'stopped'
					self.output_msg_queue.put({
						'message': '{} {}'.format(
							self.model_name,
							'is running' if self.is_running else 'stopped',
						),
					})
			else:
				log.error('''"type" key not found in data''')
				log.error('''---> data = {}'''.format(msg))
				self.state = 'stopped'

	def run(self):
		"""
		The main entry point of this nupic predictor

		:rtype: None
		"""
		try:
			self.is_started.set()
			self.state = 'started'
			self.predictor_thread()
		except KeyboardInterrupt as e:
			self.input_file.close()
			raise e
		except StopIteration as e:
			error_log_stack(e)
			raise e
		except Exception as e:
			error_log_stack(e)
			raise e

	def desired_output(self, x, r, l=0.0, m=0.5, h=1.0):
		if x < m:
			s = abs(m - l)
			o = l + s * r
			y = o
		else:
			s = abs(h - m)
			o = m + s * r
			y = o
		return y

	def compute_prediction(self, input_data, should_learn=True):
		"""
		Make a prediction from a row of input data.

		The `data` must be a string formatted like this:
			'2018-06-10 22:58:00.000000,6702.0,6709.0'

		:param input_data: The row of input data, which will be used to make a
			prediction.
		:type input_data: str
		:param should_learn:
			True - enables learning when making the prediction.
			False - disables learning when making the prediction.
		:type should_learn: bool
		:return: The prediction made by the Nupic model.
			For example:
				[{
					'time_predicted': '2018-06-10 22:59:00',
					'confidence': 100.0,
					'pct_error': 0.0,
					'actual': 0.0,
					'prediction_type': 'F',
					'exchange': 'bittrex',
					'prediction': 0.0,
					'anomaly_score': 1.0,
					'predicted_field': 'target_value',
					'timeframe': '1m',
					'market': 'btcusd',
				}]
		:rtype: list of dict
		"""
		if should_learn:
			self.enable_learning()
		else:
			self.disable_learning()
		input_msg = {
			'type': JSONMessage.TYPE_PREDICT,
			'data': input_data,
		}
		self.command_queue.put(input_msg)
		prediction = self.output_msg_queue.get()
		return prediction


predictors = {}

def get_predictor(id):
	predictor = predictors.get(id, None)
	if predictor is None:
		raise ValueError('predictor "{}" not found.'.format(id))
	return predictor

@app.route('/')
def hello_world():
	return 'Hello from the Nupic Predictor!'

@app.route('/predictors/', methods=['GET'])
def get_predictors():
	return {k:None for k, v in predictors.items()}

@app.route('/new/predictor/', methods=['POST'])
def new_predictor():
	"""
	Create a new predictor instance to the global `predictors` dictionary.

	POST form data with this format:
		'model': The Nupic model as a JSON string not a YAML string.
		'exchange': The exchange ID as a string.
		'market': The market symbol without slash (meaning '/') characters.
		'predicted_field': The field the Nupic model should predict.  NOTE:
			the predicted field should match one sent to the Nupic predictor
			in the 'sensorParams' contained in the 'model' attribute.
		'timeframe': '1m' | '5m' | '1h' | '1d' | etc...
	:return:
	"""
	data = json_loads_byteified(request.data)
	model = data['model']
	log.debug('Nupic model recieved as JSON: {}'.format(model))
	exchange = data['exchange']
	market = data['market']
	predicted_field = data['predicted_field']
	timeframe = data['timeframe']
	log.debug('exchange = {}'.format(exchange))
	log.debug('market = {}'.format(market))
	log.debug('predicted_field = {}'.format(predicted_field))
	log.debug('timeframe = {}'.format(timeframe))
	count = len(predictors) + 1
	model_identity = '{}-{}-{}-{}-{}'.format(
		count,
		exchange,
		market,
		predicted_field,
		timeframe,
	)
	model_filename_fq = os.path.join(
		os.environ['NUPIC_MODEL_DIR'],
		'{}.yaml'.format(model_identity),
	)
	log.debug('creating Nupic model file: {}'.format(model_filename_fq))
	with open(model_filename_fq, 'w') as f:
		yaml.dump(model, f)
	predictor = NupicPredictorv2(
		exchange=exchange,
		market=market,
		predicted_field=predicted_field,
		timeframe=timeframe,
		model_filename=model_filename_fq,
		model_identity=model_identity,
	)
	predictors[model_identity] = predictor
	log.debug('predictors = {}'.format(predictors))
	msg = {
		'success': True,
		'message': 'created',
		'predictor': {
			'id': model_identity,
			'model_filename': model_filename_fq,
		}
	}
	return json.dumps(msg), 201, {'ContentType': 'application/json'}

@app.route('/start/predictor/<id>/', methods=['POST'])
def start_predictor(id):
	"""
	Start a Nupic predictor initializing its input file with the header rows.

	The field 'header-json-message' in the form data must contain the
	following as a JSON string:
		[
			"timestamp, field_1, field_2, ..., field_3",
			"datetime, float, float, ..., float",
			"T, , , , ",
		]

	NOTE: The predictor must have first been created, else error is returned.

	:param id: The `model_identity` attribute of the Nupic predictor.
	:type id: str
	:return:
	"""
	log.debug('start_predictor request: {}'.format(request))
	header_rows = json_loads_byteified(request.data)
	predictor = get_predictor(id)
	predictor.start()
	msg = {
		'type': JSONMessage.TYPE_HEADER,
		'data': header_rows,
	}
	predictor.command_queue.put(msg)
	msg = predictor.output_msg_queue.get()
	msg.update({'success': True})
	return json.dumps(msg), 200, {'ContentType': 'application/json'}

@app.route('/stop/predictor/<id>/', methods=['POST'])
def stop_predictor(id):
	"""
	Stop the given Nupic predictor.

	:param id: The `model_identity` attribute of the Nupic predictor.
	:type id: str
	:return:
	"""
	predictor = get_predictor(id)
	msg = {
		'type': JSONMessage.TYPE_QUIT,
	}
	predictor.command_queue.put(msg)
	msg = predictor.output_msg_queue.get()
	msg.update({'success': True})
	return json.dumps(msg), 200, {'ContentType': 'application/json'}

@app.route('/predict/<id>/<should_learn>/', methods=['POST'])
def predict(id, should_learn):
	"""
	Make a prediction from a row of input data with learning disabled.

	The `data` field must be set like this:
		'2018-06-10 22:58:00.000000,6702.0,6709.0'

	:param id: The `model_identity` attribute of the Nupic predictor.
	:type id: str
	:param should_learn: Either: 'true' or 'false'
	:type should_learn: str
	:return: The prediction made by the Nupic model.
		For example:
			[{
				'time_predicted': '2018-06-10 22:59:00',
				'confidence': 100.0,
				'pct_error': 0.0,
				'actual': 0.0,
				'prediction_type': 'F',
				'exchange': 'bittrex',
				'prediction': 0.0,
				'anomaly_score': 1.0,
				'predicted_field': 'target_value',
				'timeframe': '1m',
				'market': 'btcusd',
			}]
	"""
	log.debug('/predict/{}/{}/ request: {}'.format(id, should_learn, request))
	input_data = json_loads_byteified(request.data)
	predictor = get_predictor(id)
	if should_learn == 'true':
		should_learn = True
	else:
		should_learn = False
	prediction = predictor.compute_prediction(input_data, should_learn=should_learn)
	prediction.update({'success': True})
	return json.dumps(prediction), 200, {'ContentType': 'application/json'}


if __name__ == "__main__":
	predictor = NupicPredictorv2(parse_args=True)
	predictor.run()



