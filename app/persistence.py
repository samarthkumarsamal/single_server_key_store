
import json
import os
import tempfile
from pathlib import Path
import logging


# Location of the persistent data file
DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "store.json"
)


def save_snapshot(snapshot):
    """
    Save a snapshot of the key-value store to disk.

    The caller must provide a stable copy of the data.
    Uses atomic file replacement to protect existing data.
    """

    # Create data directory if it does not exist
    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_path = None

    try:
        # Write snapshot into a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            prefix=".store-",
            suffix=".tmp",
            delete=False
        ) as temp_file:

            temp_path = Path(temp_file.name)

            # Serialize data efficiently
            json.dump(
                snapshot,
                temp_file,
                ensure_ascii=False,
                separators=(",", ":")
            )

            # Flush data to disk
            temp_file.flush()
            os.fsync(temp_file.fileno())

        # Atomically replace the previous snapshot
        os.replace(temp_path, DATA_FILE)

    finally:
        # Remove any leftover temporary file
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_snapshot():
    """
    Load the previously saved key-value store snapshot.

    Returns an empty dictionary if no snapshot exists.
    Raises an error if the snapshot is corrupted.
    """

    # Return empty storage on first startup
    if not DATA_FILE.exists():
        return {}

    try:
        # Read the saved JSON snapshot
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Validate snapshot structure
        if not isinstance(data, dict):
            raise ValueError(
                "Invalid snapshot: expected a dictionary"
            )

        return data

    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(
            f"Failed to load snapshot: {error}"
        ) from error


def periodic_snapshot_worker(
    store,
    stop_event,
    interval_seconds=10
):
    """
    Periodically save the key-value store to disk.

    Designed to run in a background thread.
    """

    if interval_seconds <= 0:
        raise ValueError(
            "Snapshot interval must be positive"
        )

    logger = logging.getLogger("kv_store.operations")

    while not stop_event.wait(interval_seconds):
        try:
            # Create a consistent in-memory snapshot
            snapshot = store.snapshot()

            # Write snapshot outside the dictionary lock
            save_snapshot(snapshot)

        except Exception:
            # Record error and continue running
            logger.exception(
                "SNAPSHOT failed"
            )
