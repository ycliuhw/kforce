import pickle


class CacheModule(object):
    """
    A caching module backed by pickle files.
    """

    def _load(self, filepath):
        # Pickle is a binary format
        with open(filepath, 'rb') as f:
            return pickle.load(f, encoding='bytes')

    def _dump(self, value, filepath):
        with open(filepath, 'wb') as f:
            # Use pickle protocol 2 which is compatible with Python 2.3+.
            pickle.dump(value, f, protocol=2)
