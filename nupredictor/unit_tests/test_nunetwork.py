from unittest import TestCase, skip
import re, os, json, io, sys, subprocess as sp, mock
from random import randint
from datetime import datetime, timedelta
from time import sleep
import numpy as np
import nupic
from dateutil import parser
from nupredictor.nunetwork import *
from nupredictor.functions import get_files
from socket import gethostname, getfqdn
from nupic.data.file_record_stream import FileRecordStream
import threading
import multiprocessing as mp
from timeout_wrapper import timeout


def heading(msg):
	header = '\n\n' + '-'*100 + "\n\n"
	return "{}{}{}".format(header, msg, header)


class Predictor_Functions(TestCase):

	def setUp(self):
		self.start = datetime(2018, 1, 1)
		self.end = self.start + timedelta(days=30)
		self.format = "%Y-%m-%d %H:%M:%S.000000"

	# test: calculate_start_date()

	def test_calculate_start_date___with_1d_time_units(self):
		# inputs
		end_date = datetime(2018, 12, 31)
		data_points = 365
		time_units = '1d'

		# expected outputs
		eO = end_date - timedelta(days=data_points)

		# call the method
		aO = calculate_start_date(end_date=end_date, data_points=data_points, time_units=time_units)

		# verify
		self.assertEqual(eO, aO)

	# test: get_start_dates()

	def test_get_start_dates____with_1m_time_units(self):
		# inputs
		data_points = 3000
		start = self.start
		td = timedelta(minutes=500)
		time_units = '1m'

		# expected outputs
		eO_dates = [
			start,
			start + td,
			start + td * 2,
			start + td * 3,
			start + td * 4,
			start + td * 5,
			]

		# call the method under test
		aO_dates = get_start_dates(start_dt=start, data_points=data_points, time_units=time_units)

		# verify the data type
		self.assertIsInstance(aO_dates, list)

		# verify the number if items in the returned list
		self.assertEqual(len(eO_dates), len(aO_dates), heading("Expected {} items returned, but got {}".format(len(eO_dates), len(aO_dates))))

		# verify each date in the list is correct
		for eO_date in eO_dates:
			self.assertIn(eO_date, aO_dates,
						  heading("Expected {} in the returned list of dates\n\nBut, got:\n{}".format(eO_date, aO_dates)))

	def test_get_start_dates____with_1d_time_units(self):
		# inputs
		data_points = 3000
		time_units = '1d'
		end = self.start
		start = calculate_start_date(end_date=end, data_points=data_points, time_units=time_units)
		td = timedelta(days=500)

		# expected outputs
		eO_dates = [
			start,
			start + td,
			start + td * 2,
			start + td * 3,
			start + td * 4,
			start + td * 5,
			]

		# call the method under test
		aO_dates = get_start_dates(start_dt=start, data_points=data_points, time_units=time_units)

		# verify the data type
		self.assertIsInstance(aO_dates, list)

		# verify the number if items in the returned list
		self.assertEqual(len(eO_dates), len(aO_dates), heading("Expected {} items returned, but got {}".format(len(eO_dates), len(aO_dates))))

		# verify each date in the list is correct
		for eO_date in eO_dates:
			self.assertIn(eO_date, aO_dates,
						  heading("Expected {} in the returned list of dates\n\nBut, got:\n{}".format(eO_date, aO_dates)))

	# test: get_data()

	@skip("Need to re-write this test case, so it imports a fixture for the data it will export in the test")
	def test_get_data___with_1m_time_units____and_3000_data_points(self):
		# inputs
		start = self.start
		filename = INPUT_FILE_PATH
		data_points = 3000
		time_unit = '1m'

		# expected outputs
		line_count = 3003
		line1 = 'timestamp, consumption\n'
		line2 = 'datetime, float\n'
		line3 = 'T, \n'
		line4 = r'\d{4}-\d{2}-\d{2} \d{2}[:]\d{2}[:]\d{2}[.]\d{6}, \d0[.]\d+'
		line4_ptn = re.compile(line4, re.DOTALL)

		# call the method under test
		cache_input_data_file(start=start, data_points=data_points, time_units=time_unit)

		# open the file just created
		with open(filename, 'r') as f:
			lines = f.readlines()

		# verify number of lines in the file
		self.assertEqual(line_count, len(lines),
						 heading("Expected {} lines in the file, but got {}".format(line_count, len(lines))))

		# verify the first three lines in the file
		self.assertEqual(line1, lines[0])
		self.assertEqual(line2, lines[1])
		self.assertEqual(line3, lines[2])

		# verify the other lines in the file
		for i in range(3, len(lines)):
			# verify the pattern of the line
			line = lines[i]
			did_match = not line4_ptn.search(line)
			self.assertTrue(did_match, heading("Expected pattern {}".format(line4)))

			# verify the timestamp column
			timestamp = line.split(',')[0]
			eO_timestamp = (start + timedelta(minutes=1) * (i - 3)).strftime(self.format)
			self.assertEqual(timestamp, eO_timestamp,
							 heading("Expected the timestamp column = {}, but got {}".format(eO_timestamp, timestamp)))

	# test: write_input_file()

	@skip("Need to re-write this test case, so it imports a fixture for the data it will export in the test")
	def test_write_input_file___with_1d_time_units(self):
		# globals
		global INPUT_FILENAME, DATA_TABLE

		# inputs
		exchange = 'bitmex'
		markets = ['BTC/USD']
		start = self.start
		end = self.end
		filename = INPUT_FILENAME
		time_unit = '1h'

		# expected outputs
		line_count = 3003
		line1 = 'timestamp, consumption\n'
		line2 = 'datetime, float\n'
		line3 = 'T, \n'
		line4 = r'\d{4}-\d{2}-\d{2} \d{2}[:]\d{2}[:]\d{2}[.]\d{6}, \d0[.]\d+'
		line4_ptn = re.compile(line4, re.DOTALL)

		# call the methods under test
		market_data = fetch_market_data(exchange=exchange, markets=markets,
										data_table=DATA_TABLE, timeframe=time_unit,
										start=start, end=end,
										host=django_server, port=django_port)
		initialize_csv(input_filename, markets,
					   include_spread=include_spread, include_classification=include_classification)
		write_input_file(input_filename, markets, market_data, spread_as_pct=True,
						 include_spread=include_spread, include_classification=include_classification)

		# open the file just created
		with open(filename, 'r') as f:
			lines = f.readlines()

		# verify number of lines in the file
		self.assertEqual(line_count, len(lines),
						 heading("Expected {} lines in the file, but got {}".format(line_count, len(lines))))

		# verify the first three lines in the file
		self.assertEqual(line1, lines[0])
		self.assertEqual(line2, lines[1])
		self.assertEqual(line3, lines[2])

		# verify the other lines in the file
		for i in range(3, len(lines)):
			# verify the pattern of the line
			line = lines[i]
			did_match = not line4_ptn.search(line)
			self.assertTrue(did_match, heading("Expected pattern {}".format(line4)))

			# verify the timestamp column
			timestamp = line.split(',')[0]
			eO_timestamp = (start + timedelta(minutes=1) * (i - 3)).strftime(self.format)
			self.assertEqual(timestamp, eO_timestamp,
							 heading("Expected the timestamp column = {}, but got {}".format(eO_timestamp, timestamp)))

	# test: get_services()

	@skip("Need to re-write this test, so that it doesn't depend on a running Django server.")
	def test_get_services(self):
		"""
		REQUIRED! This test cases requires a Django server to be running on port 8000 and have
				  a "running" service (meaning a Service record in the database with its state = 'Running'

		:rtype: None
		"""

		# inputs
		django_server_name = gethostname()
		url = 'http://{}:8000/ws/service/'.format(django_server_name)
		username = 'mellertson'
		password = '!cR1BhRtJCbCjBCQu&%q'

		# expected output
		eO = { 'hostname': getfqdn(gethostname()), 'port': 52000 }

		# call the method under test
		aO = get_services(url, username, password)

		# verify
		self.assertIn('authkey', aO)
		eO.update({'authkey': aO['authkey']})
		self.assertDictEqual(eO, aO)

	# test: build_input_record()

	def build_input_record(self, fields, values):
		r = {}
		for i in range(len(fields)):
			r[fields[i]] = values[i]
		return r

	# test: FileRecordStream()

	def test_file_record_stream____using_tmp_buf_file(self):
		# setup
		cwd = os.path.dirname(os.path.abspath(__file__))
		MODEL_FILE = os.path.join(cwd, 'nupic_network_model.yaml')
		CSV_FILE = os.path.join(cwd, 'nupic_network_input_data.csv')
		nupic = NupicPredictor(topic='trade', exchange='hitbtc2',
							   market='BTC/USDT', predicted_field='btcusd_open', timeframe='1m',
							   magic_number=400, model_filename=MODEL_FILE)
		BUF_FILE = nupic.input_filename
		with open(BUF_FILE, 'w') as buf:
			with open(CSV_FILE, 'r') as csv_file:
				# setup: write header row to nupic data source
				buf.write(csv_file.readline())
				buf.flush()
				buf.write(csv_file.readline())
				buf.flush()
				buf.write(csv_file.readline())
				buf.flush()

				# setup: initialize the Nupic network
				data_source = FileRecordStream(BUF_FILE)
				network = nupic.create_network(data_source)
				nupic.configure_network(network)

				# test: run 5 records through the model
				last_p = None
				for i in range(5):
					buf.write(csv_file.readline())
					buf.flush()
					network.run(1)
					classifierResults = getPredictionResults(network, "classifier")
					p = classifierResults[1]["predictedValue"]
					self.assertIsInstance(p, np.float32)
					self.assertIsInstance(classifierResults, dict)
					self.assertNotEqual(p, last_p)
					last_p = p

	# test: run()

	def test_run____using_tmp_buf_file(self):
		# setup
		cwd = os.path.dirname(os.path.abspath(__file__))
		MODEL_FILE = os.path.join(cwd, 'nupic_network_model.yaml')
		CSV_FILE = os.path.join(cwd, 'nupic_network_input_data.csv')
		os.environ['CODE_HOME'] = '/opt'
		self.cmd_line = [
			'/opt/python_envs/nupic/bin/python',
			os.path.join(os.environ['CODE_HOME'],
						 'spread-predictor/nupredictor/nunetwork.py'),
			'--topic', 'trade',
			'--exchange', 'hitbtc2',
			'--market', 'BTC/USDT',
			'--timeframe', '1m',
			'--predicted-field', 'btcusd_open',
			'--model', MODEL_FILE,
		]
		nupic = sp.Popen(self.cmd_line, stdin=sp.PIPE, stdout=sp.PIPE,
						 stderr=sp.PIPE)
		with open(CSV_FILE, 'r') as csv_file:
			nupic.stdin.write(json.dumps({'header_row': csv_file.readline()}))
			nupic.stdin.write('\n')
			nupic.stdin.flush()
			nupic.stdin.write(json.dumps({'header_row': csv_file.readline()}))
			nupic.stdin.write('\n')
			nupic.stdin.flush()
			nupic.stdin.write(json.dumps({'header_row': csv_file.readline()}))
			nupic.stdin.write('\n')
			nupic.stdin.flush()
			for i in range(5):
				line = csv_file.readline()
				nupic.stdin.write(json.dumps({'description': 'raw', 'data': line}))
				nupic.stdin.write('\n')
				nupic.stdin.flush()
				try:
					line = nupic.stdout.readline()
					p = json.loads(line)
					self.assertIsInstance(p, dict)
					self.assertIsInstance(parser.parse(p['predicted_time']), datetime)
					self.assertEqual(p['market_id'], 'hitbtc2-BTC/USDT')
					self.assertEqual(p['timeframe'], '1m')
					self.assertIsInstance(p['value'], float)
					self.assertEqual(str(p['value_str']), str(p['value']))
					self.assertIsInstance(p['confidence'], float)
					self.assertEqual(p['data_type'], 'float')
					self.assertEqual(p['predictor'], 'nupic')
					self.assertEqual(p['type'], 'F')
					print('Prediction received: {}'.format(p))
				except ValueError as e:
					nupic.kill()
					lines = nupic.stderr.readlines()
					if len(lines) <= 0:
						lines = ''
					msg = '{} {}'.format(lines, str(e))
					self.assertTrue(False, msg)

			nupic.stdin.write(json.dumps({'description': 'command', 'data': 'quit'}))
			nupic.stdin.write('\n')
			nupic.stdin.flush()


class Modify_Output_File(TestCase):
	""" Test the modify_output_file_permissions function """

	def setUp(self):
		directory = os.path.dirname(os.path.abspath(__file__))
		self.directory = os.path.join(directory, 'test_files')
		self.cmd = 'chmod 644 {}/*.txt'.format(self.directory)
		os.system(self.cmd)

	def tearDown(self):
		os.system(self.cmd)

	def test_modify_output_file_permissions(self):
		# inputs
		all_files = { 'file1.txt': False , 'file2.txt': False, }
		all_lines_ran = False

		# execute the method being tested
		modify_output_file_permissions(self.directory)

		# for each file in the directory...
		for file in get_files(directory=self.directory):
			fq_file = os.path.join(self.directory, file)
			other_perms = get_file_permissions(fq_filename=fq_file)[2]

			self.assertGreaterEqual(int(other_perms), 6,
									'Expected "other permissions" to be at least read/write, but got {}'.format(other_perms))
			all_files[file] = True

		# verify all lines in this test case ran
		for filename, did_run in all_files.items():
			self.assertTrue(did_run, 'Permissions on file "{}" was not modified'.format(filename))
			all_lines_ran = True
		self.assertTrue(all_lines_ran, 'All lines in this test case were not executed')


class NupicPredictor_Tests(TestCase):

	def setUp(self):
		self.to_queue = mp.Queue()
		self.from_queue = mp.Queue()
		self.topic = 'trade'
		self.exchange_id = 'hitbtc2'
		self.market = 'BTC/USDT'
		self.predicted_field = 'btcusd_close'
		self.timeframe = '1m'
		self.model_filename = 'nupic_network_model.yaml'
		self.predictor = NupicPredictor(
			topic=self.topic,
			exchange=self.exchange_id,
			market=self.market,
			predicted_field=self.predicted_field,
			timeframe=self.timeframe,
			model_filename=self.model_filename)

		# mock
		self.predictor.get_next_data = self.get_next_data
		self.predictor.output_message = self.output_message

		# start the predictor thread
		self.predictor.start()
		self.predictor.is_started.wait()

	def tearDown(self):
		# shutdown
		self.to_queue.put(JSONMessage.build(
			JSONMessage.TYPE_QUIT, 'quit'))
		os.remove(self.predictor.input_filename)

	def get_next_data(self):
		data = self.to_queue.get()
		data = str(data)
		data = json.loads(data)
		return data

	def output_message(self, message):
		self.from_queue.put(message)
		return message

	# test: __init__()

	@mock.patch(target='random.randint')
	def test__init__(self, rint):
		# setup
		rint.return_value = 500

		# test
		p = NupicPredictor(
			topic=self.topic,
			exchange=self.exchange_id,
			market=self.market,
			predicted_field=self.predicted_field,
			timeframe=self.timeframe,
			model_filename=self.model_filename)
		input_filename = '/tmp/500-{}.csv'.format(p.name)

		# verify
		self.assertEqual(self.topic, p.topic)
		self.assertEqual(self.exchange_id, p.options.exchange_id)
		self.assertEqual(self.exchange_id, p.exchange_id)
		self.assertEqual(self.market, p.symbol)
		self.assertEqual(self.market, p.options.market)
		self.assertEqual(self.predicted_field, p.options.predicted_field)
		self.assertEqual(self.predicted_field, p.predicted_field)
		self.assertEqual(self.timeframe, p.options.timeframe)
		self.assertEqual(self.timeframe, p.timeframe)
		self.assertEqual(DateTimeUtils.string_to_timeframe(self.timeframe), p.timeframe_td)
		self.assertEqual(self.model_filename, p.options.model)
		self.assertEqual(self.model_filename, p.model_filename)
		self.assertEqual(input_filename, p.input_filename)
		self.assertIsInstance(p.input_file, file)
		self.assertFalse(p.input_file.closed)

	# test: predictor_thread()

	def test_predictor_thread____send_header_message(self):
		# test: send header row to the predictor
		msg = JSONMessage.build(JSONMessage.TYPE_HEADER, {
			'row1': "timestamp, btcusd_open, btcusd_high, btcusd_low, btcusd_close, btcusd_volume, btcusd_lastSize",
			'row2': "datetime, float, float, float, float, float, float",
			'row3': "T,  ,  ,  ,  ,  ,  ",
		})
		json_msg = json.dumps(msg)
		self.to_queue.put(json_msg)

		# verify the confirmation message
		msg = self.from_queue.get(timeout=5)
		self.assertIn('type', msg)
		self.assertEqual(JSONMessage.TYPE_NET_INITIALIZED, msg['type'])
		self.assertIn('message', msg)
		self.assertEqual(msg['message'], 'The Nupic network was successfully initialized')

		# verify
		self.assertIsInstance(self.predictor.network, nupic.engine.Network)

	def disable_learning(self, network):
		print('disable learning called...')

	def enable_learning(self, network):
		print('enable learning called...')

	@mock.patch(target='nupredictor.nunetwork.enableLearning')
	@mock.patch(target='nupredictor.nunetwork.disableLearning')
	def test_predictor_thread____send_predict_message(self, m_dlearn, m_elearn):
		# setup
		self.test_predictor_thread____send_header_message()
		m_dlearn.side_effect = self.disable_learning
		m_elearn.side_effect = self.enable_learning

		# test
		msg = JSONMessage.build(
			JSONMessage.TYPE_PREDICT,
			{
				'row':'2018-06-10 22:58:00.000000,6702.0,6709.0,6693.0,6708.5,5802146.0,800.0',
				'timestamp': '2018-06-10 22:58:00.000000',
			})
		self.to_queue.put(json.dumps(msg))

		# verify
		try:
			msg = self.from_queue.get(timeout=5)
		except:
			self.assertTrue(False, 'timed out waiting for the prediction')
		self.assertIn('type', msg)
		self.assertEqual(JSONMessage.TYPE_PREDICTION_RESULT, msg['type'])
		self.assertIn('message', msg)
		self.assertIsInstance(msg['message'], Prediction)
		self.assertEqual(1, m_dlearn.call_count)
		self.assertEqual(0, m_elearn.call_count)

	@mock.patch(target='nupredictor.nunetwork.enableLearning')
	@mock.patch(target='nupredictor.nunetwork.disableLearning')
	def test_predictor_thread____send_training_message(self, m_dlearn, m_elearn):
		# setup
		self.test_predictor_thread____send_header_message()
		m_dlearn.side_effect = self.disable_learning
		m_elearn.side_effect = self.enable_learning

		# test: send "train Nupic" message
		msg = JSONMessage.build(
			JSONMessage.TYPE_TRAIN_NUPIC,
			{
				'row': '2018-06-10 22:58:00.000000,6702.0,6709.0,6693.0,6708.5,5802146.0,800.0',
				'timestamp': '2018-06-10 22:58:00.000000',
			})
		self.to_queue.put(json.dumps(msg))

		# verify: "trainining confirmed" message received
		try:
			msg = self.from_queue.get(timeout=5)
		except:
			self.assertTrue(False, 'timed out waiting for the prediction')
		self.assertIn('type', msg)
		self.assertEqual(JSONMessage.TYPE_TRAIN_CONFIRMATION, msg['type'])
		self.assertEqual(0, m_dlearn.call_count)
		self.assertEqual(1, m_elearn.call_count)





























