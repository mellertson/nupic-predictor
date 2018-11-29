#!/usr/bin/env python
import re
import json
import os, errno, shutil
import sys
import yaml
import requests
import pandas as pd
import pytz
import traceback
from subprocess import Popen
from dateutil import parser, tz
from datetime import datetime, timedelta
from nupic.engine import Network
from nupic.encoders import MultiEncoder
from nupic.data.file_record_stream import FileRecordStream
from optparse import OptionParser
from nupredictor.functions import get_files
from nupredictor.utilities import parse_time_units
from random import randint
from socket import getfqdn, gethostname
from threading import Thread


SUBSCRIBED = 1
UNSUBSCRIBED = 2
INVALID_REQUEST = 400


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

	# classes
	'DateTimeUtils',
	'NupicPredictor',
]


def error_log_stack(e):
	"""
	Outputs the curret stack trace and the exception's text to the root error logger

	:param e:
	:type e: Exception
	"""

	ss = traceback.extract_tb(sys.exc_info()[2])
	stack = traceback.format_list(ss)
	sys.stderr.writelines(stack)
	sys.stderr.writelines([''])
	sys.stderr.writelines(['Exception: {}'.format(e)])


class DateTimeUtils(object):
	FMT = "%m/%d/%Y %I:%M %P (%Z)"
	utc_zone = tz.tzutc()
	local_zone = tz.tzlocal()
	ptn = re.compile(r'(?P<value>[\d]+)(?P<units>[mhd])')

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
			Choices are: '15m' | '30m' | '1m' | '5m' | '1h' | '1d'
		:type timeframe: str

		:return:
			A timedelta equivilent to the 'timeframe' argument
		:rtype: timedelta
		"""

		m = cls.ptn.search(timeframe)
		if m:
			value = int(m.group('value'))
			units = m.group('units')
			if units == 'm':
				return timedelta(minutes=value)
			elif units == 'h':
				return timedelta(hours=value)
			elif units == 'd':
				return timedelta(days=value)
			else:
				msg = 'Invalid "timeframe" parameter: {}'.format(timeframe)
				raise ValueError(msg)

	@classmethod
	def format_usa(cls, dt):
		return dt.strftime(cls.FMT)


class Prediction(object):
	def __init__(self, time_predicted, exchange, market, timeframe,
				 prediction_type, prediction, confidence, actual, pct_error):
		self.time_predicted = time_predicted
		self.exchange = exchange
		self.market = market
		self.timeframe = timeframe
		self.prediction_type = prediction_type
		self.prediction = prediction
		self.confidence = confidence
		self.actual = actual
		self.pct_error = pct_error

	def to_dict(self):
		"""
		Converts the prediction to a python dictionary

		:rtype: dict
		"""
		return {
			'predicted_time': self.time_predicted,
			'market_id': '{}-{}'.format(self.exchange, self.market),
			'timeframe': self.timeframe,
			'value': self.prediction,
			'value_str': str(self.prediction),
			'confidence': self.confidence,
			'actual_value': self.actual,
			'actual_value_str': str(self.actual),
			'pct_diff': self.pct_error,
			'attribute': None,
			'data_type': 'float',
			'predictor': 'nupic',
			'data_set': None,
			'type': self.prediction_type,
		}


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
					  username='mellertson', password='test', host='localhost', port=8000,
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


def build_model(fq_input_filename, fq_model_filename, predicted_field):
	"""
	Build and initialize a Nupic network (model)

	:param fq_input_filename: The fully qualified path to the Nupic formatted input file name
	:type fq_input_filename: str
	:param fq_model_filename: The fully qualified path to the Nupic model parameters (in YAML format)
	:type fq_model_filename: str
	:param predicted_field: The "fieldname", identified in the model parameters file, which will be predicted, e.g. "spread" or "m1_ask"
	:type predicted_field: str

	:rtype: nupic.engine.Network
	"""

	# Create a data source for the network.
	dataSource = FileRecordStream(streamID=fq_input_filename)
	network = createNetwork(dataSource=dataSource, fq_model_filename=fq_model_filename)

	# Configure the network according to the model parameters
	configureNetwork(network=network, predicted_field=predicted_field)
	return network


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


class NupicPredictor(Thread):
	"""
	A predictor which constructs and uses a Nupic model

	:ivar predicted_field:
			The "fieldname", identified in the model parameters file,
			which will be predicted, e.g. "spread" or "m1_ask"
	:type predicted_field: str
	"""

	def __init__(self, topic=None, exchange=None, market=None,
				 predicted_field=None, timeframe=None,
				 parse_args=False, model_filename=None,
				 input_stream=sys.stdin, output_stream=sys.stdout):
		super(NupicPredictor, self).__init__(
			target=self.run, name='NupicPredictor.run')
		if parse_args:
			self.options = self.parse_options()[0]
		else:
			self.options = self
			self.options.topic = topic
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
		self.model_fqfn = self.build_dir(self.model_filename)
		self.results_fqfn = self.build_dir('results.csv')
		self.topic = self.options.topic
		self.exchange_id = self.options.exchange
		self.symbol = self.options.market
		self.symbol_fixed = self.options.market.replace('/', '')
		self.predicted_field = self.options.predicted_field
		self.timeframe = self.options.timeframe
		self.timeframe_td = DateTimeUtils.string_to_timeframe(self.timeframe)
		self.name = '{}-{}-{}-{}-{}'.format(
			self.topic,
			self.exchange_id,
			self.symbol_fixed,
			self.predicted_field,
			self.timeframe)
		self.input_filename = '/tmp/{}-{}.csv'.format(
			randint(1, 999999999), self.name)
		self.input_file = open(self.input_filename, 'w+')
		self.input_stream = input_stream
		self.output_stream = output_stream

	def __del__(self):
		if not self.input_file.closed:
			self.input_file.close()
		Popen(['rm', 'self.input_file'])

	def __str__(self):
		return self.name

	def __repr__(self):
		return self.__str__()

	def build_dir(self, filename):
		return os.path.join(self.dir, filename)

	def parse_options(self):
		"""
		Parse command line options and return them

		:returns: (options, args)
		:rtype: tuple
		"""

		usage = "usage: $prog [options]"
		parser = OptionParser(usage)
		parser.add_option('-x', '--exchange', dest='exchange',
			default='hitbtc2',
			help='the exchange ID, e.g. "hitbtc2" or "bittrex".')
		parser.add_option('-m', "--market", dest="market",
			default="BTC/USD",
			help='a standardized market symbol (default = "BTC/USD")')
		parser.add_option('-t', "--timeframe", dest="timeframe",
			default='1m',
			help='the time units, either: "1m", "5m", "1h", "1d" (default = "1m")')
		parser.add_option('-P', "--predicted-field", dest="predicted_field",
			default='btcusd_high',
			help="""the field name that will be predicted, 
			e.g. 'btcusd_high' | 'btcusd_low' (default = "btcusd_high")""")
		parser.add_option('--topic', dest='topic',
			default='trade',
			help="The subscription topic of the data which will be sent to Nupic")
		parser.add_option('--model', dest='model',
			default='nupic_predict_buys_sells_model.yaml')

		(options, args) = parser.parse_args()
		return options, args

	def create_network(self, data_source):
		"""
		Create and initialize the Nupic model (a.k.a. Network)

		:param data_source: The input data source for the Nupic model
		:type data_source: FileRecordStream

		:returns: A fully initialized Nupic model (a.k.a. Network)
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
		network.regions["SP"].setParameter("learningMode", 1)
		network.regions["TM"].setParameter("learningMode", 1)
		network.regions["classifier"].setParameter("learningMode", 1)

		# Enable inference for all regions
		network.regions["SP"].setParameter("inferenceMode", 1)
		network.regions["TM"].setParameter("inferenceMode", 1)
		network.regions["classifier"].setParameter("inferenceMode", 1)
		return network

	def run(self):
		"""
		The main entry point of this nupic predictor

		:rtype: None
		"""

		try:
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

	def predictor_thread(self):
		i = 0
		network = None
		while True:
			data = self.get_next_data()
			if 'header_row' in data:
				self.input_file.write(data['header_row'])
				self.input_file.flush()
				i += 1
				if i >= 3:
					data_source = FileRecordStream(self.input_filename)
					network = self.create_network(data_source)
					network = self.configure_network(network)
			elif data['description'] == 'command':
				if data['data'].lower() == 'quit':
					exit(0)
			elif data['description'] == 'trade':
				self.input_file.write(data['data'])
				self.input_file.flush()
				p = self.get_next_prediction(network, data)
				self.output_prediction(p)
			elif data['description'] == 'raw':
				self.input_file.write(data['data'])
				self.input_file.flush()
				p = Prediction(
					time_predicted=str(datetime.now(tz=pytz.UTC)),
					exchange=self.exchange_id,
					market=self.symbol,
					timeframe=self.timeframe,
					prediction_type='F',
					prediction=1000.0,
					confidence=1.0,
					actual=None,
					pct_error=0.0)
				self.output_prediction(p)

	def get_next_data(self):
		"""
		Read next data point from standard input

		:rtype:  dict
		"""

		try:
			# block until the next trade or command is recieved
			json_data = self.input_stream.readline()
			data = json.loads(json_data)
			return data
		except EOFError:
			exit(1)

	def get_next_prediction(self, network, data):
		"""
		run the Nupic predictor, save the results to the 'model_output_files' directory

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
		tp = data['time_closed'] + self.timeframe_td
		p = Prediction(
			time_predicted=str(tp),
			exchange=self.exchange_id,
			market=self.symbol,
			timeframe=self.timeframe,
			prediction_type='F',
			prediction=predicted_value,
			confidence=confidence * 100,
			actual=None,
			pct_error=None)
		return p

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

		json_string = json.dumps(prediction.to_dict())
		self.output_stream.write(json_string)
		self.output_stream.write('\n')
		self.output_stream.flush()
		return json_string


if __name__ == "__main__":
	predictor = NupicPredictor(parse_args=True)
	predictor.start()
	predictor.join()














