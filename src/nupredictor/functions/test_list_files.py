import unittest
import os
from . import get_files


class Get_Files_Tests(unittest.TestCase):
    def test_get_files_function(self):
        # inputs
        directory = os.path.dirname(os.path.realpath(__file__))
        sub_dir = os.path.join(directory, 'files')


        # expected outputs
        eO = ['file1.txt', 'file2.txt', 'file3.txt']
        eO_len = len(eO)

        # call the method under test
        aO = get_files(directory=sub_dir)

        # verify
        self.assertIsInstance(aO, list, 'Expected "list" as return value, but got "{}"'.format(type(aO)))
        aO_len = len(aO)
        self.assertEqual(eO_len, aO_len, 'Expected {} filenames, but got {}'.format(eO_len, aO_len))
        for filename in eO:
            self.assertIn(filename, aO, 'Filename: "{}" was not found in "{}"'.format(filename, directory))




