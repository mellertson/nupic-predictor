import os


__all__ = ['get_files']


def get_files(directory):
    """
    Return a list of all files in the directory

    :param directory:
    :type directory: str
    :return: List of file names
    :rtype: list
    """
    for dirpath, dirnames, filenames in os.walk(directory):
        return filenames

