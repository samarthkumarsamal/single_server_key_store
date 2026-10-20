
import threading


class KeyValueStore:
    """
    Thread-safe in-memory key-value store.
    """

    def __init__(self):
        # In-memory storage
        self._data = {}

        # Lock for thread-safe operations
        self._lock = threading.Lock()

    def get(self, key):
        """
        Retrieve a value by key.
        Raises KeyError if the key does not exist.
        """
        with self._lock:
            if key not in self._data:
                raise KeyError(f"Key '{key}' not found")

            return self._data[key]

    def put(self, key, value):
        """
        Insert or update a key-value pair.
        Returns True if new, False if updated.
        """
        with self._lock:
            is_new = key not in self._data
            self._data[key] = value
            return is_new

    def delete(self, key):
        """
        Delete a key-value pair.
        Raises KeyError if the key does not exist.
        """
        with self._lock:
            if key not in self._data:
                raise KeyError(f"Key '{key}' not found")

            del self._data[key]
            return True

    
    def snapshot(self):
        """
        Create a thread-safe snapshot of the key-value store.

        Returns a consistent copy of the dictionary
        without exposing the original shared storage.
        """
        with self._lock:
            return self._data.copy()

    
    def restore(self, data):
        """
        Restore the key-value store from a saved snapshot.

        This method should be called during server startup,
        before accepting client requests.
        """

        # Validate snapshot data
        if not isinstance(data, dict):
            raise ValueError(
                "Snapshot data must be a dictionary"
            )

        # Safely replace the existing dictionary
        with self._lock:
            self._data = data.copy()

