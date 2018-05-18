from unittest import TestCase
import re
from datetime import datetime, timedelta
import os
from .nunetwork import *
from .functions import get_files


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


class Modify_Output_File(TestCase):
  """ Test the modify_output_file_permissions function """

  def setUp(self):
    directory = os.path.dirname(os.path.realpath(__file__))
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








