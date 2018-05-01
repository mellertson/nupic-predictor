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

  def test_get_start_dates(self):
    # inputs
    start = self.start
    td = timedelta(minutes=500)

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
    aO_dates = get_start_dates(start_dt=start)

    # verify the data type
    self.assertIsInstance(aO_dates, list)

    # verify the number if items in the returned list
    self.assertEqual(len(eO_dates), len(aO_dates), heading("Expected {} items returned, but got {}".format(len(eO_dates), len(aO_dates))))

    # verify each date in the list is correct
    for eO_date in eO_dates:
      self.assertIn(eO_date, aO_dates,
        heading("Expected {} in the returned list of dates\n\nBut, got:\n{}".format(eO_date, aO_dates)))

  def test_get_data(self):
    # inputs
    start = self.start
    filename = INPUT_FILE_PATH

    # expected outputs
    line_count = 3003
    line1 = 'timestamp, consumption\n'
    line2 = 'datetime, float\n'
    line3 = 'T, \n'
    line4 = r'\d{4}-\d{2}-\d{2} \d{2}[:]\d{2}[:]\d{2}[.]\d{6}, \d0[.]\d+'
    line4_ptn = re.compile(line4, re.DOTALL)

    # call the method under test
    get_data(start_dt=start)

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




