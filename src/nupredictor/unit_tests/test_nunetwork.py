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
import threading, logging
import multiprocessing as mp
from timeout_wrapper import timeout

logger = logging.getLogger('nupic_predictor')
logger.setLevel(logging.DEBUG)


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
		nupic = NupicPredictor(
			predicted_field='btcusd_open',
			model_filename=MODEL_FILE)
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


@skip('need to see if other tests pass')
class NupicPredictor_Tests(TestCase):

	def setUp(self):
		self.to_queue = mp.Queue()
		self.from_queue = mp.Queue()
		self.topic = 'trade'
		self.exchange_id = 'bittrex'
		self.market = 'BTC/USDT'
		self.predicted_field = 'btcusd_close'
		self.timeframe = '1m'
		self.model_filename = 'nupic_network_model.yaml'
		self.predictor = NupicPredictor(
			predicted_field=self.predicted_field,
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
		logger.debug('data = ' + data)
		logger.debug('type of data = ' + str(type(data)))
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
			predicted_field=self.predicted_field,
			model_filename=self.model_filename)
		input_filename = '/tmp/{}-500.csv'.format(p.name)

		# verify
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
		# HIGH: pipe predict messages as JSON into stdin
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
		json_msg = json.dumps(msg)
		self.to_queue.put(json_msg)

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
































