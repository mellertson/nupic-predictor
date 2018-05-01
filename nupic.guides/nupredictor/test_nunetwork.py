from unittest import TestCase
import re
from datetime import datetime, timedelta
from . import *


def heading(msg):
  header = '\n\n' + '-'*100 + "\n\n"
  return "{}{}{}".format(header, msg, header)


class Predictor_Functions(TestCase):
  def setUp(self):
    self.start = datetime(2018, 1, 1)
    self.format = "%Y-%m-%d %H:%M:%S.000000"

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
    get_data(start_dt=start, data_points=data_points, time_unit=time_unit)

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

  def test_get_data___with_1d_time_units____and_3000_data_points(self):
    # inputs
    start = self.start
    filename = INPUT_FILE_PATH
    data_points = 3000
    time_unit = '1h'

    # expected outputs
    line_count = 3003
    line1 = 'timestamp, consumption\n'
    line2 = 'datetime, float\n'
    line3 = 'T, \n'
    line4 = r'\d{4}-\d{2}-\d{2} \d{2}[:]\d{2}[:]\d{2}[.]\d{6}, \d0[.]\d+'
    line4_ptn = re.compile(line4, re.DOTALL)

    # call the method under test
    get_data(start_dt=start, data_points=data_points, time_unit=time_unit)

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




