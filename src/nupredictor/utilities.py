from datetime import timedelta
import re
import time


def parse_time_units(time_units):
	"""

	:param time_units: Choices are: '1m' | '5m' | '1h' | '1d'
	:type time_units: str

	:return: A timedelta equivilent to the 'timeframe' argument
	:rtype: timedelta
	"""

	RECORD_COUNT = 2000

	ptn = re.compile(r'(?P<value>[\d])(?P<units>[mhd])')
	m = ptn.search(time_units)
	if m:
		value = int(m.group('value'))
		units = m.group('units')
		if units == 'm':
			return timedelta(minutes=value * RECORD_COUNT)
		elif units == 'h':
			return timedelta(hours=value * RECORD_COUNT)
		elif units == 'd':
			return timedelta(days=value * RECORD_COUNT)
		else:
			raise ValueError('Invalid "timeframe" parameter: {}'.format(time_units))

def local_timezone():
	"""
	Returns the 3 letter code for the local timezone, accouting for daylight savings time

	:return: The 3 letter timezone code
	:rtype: str
	"""
	return time.tzname[time.daylight]








