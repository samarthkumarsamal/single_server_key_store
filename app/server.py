
import logging
import os
from threading import Event, Thread

from flask import Flask, jsonify, request

from kv_store import KeyValueStore
from logger import configure_operation_logger
from persistence import (
    load_snapshot,
    periodic_snapshot_worker,
    save_snapshot,
)


# --------------------------------------------------
# FLASK APPLICATION INITIALIZATION
# --------------------------------------------------

app = Flask(__name__)

# Suppress routine Werkzeug access logs.
# Error messages remain enabled.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Configure the server's listening address.
# Local execution: 127.0.0.1
# Docker execution: 0.0.0.0 (set through HOST)
SERVER_HOST = os.getenv("HOST", "127.0.0.1")
SERVER_PORT = 8080


# --------------------------------------------------
# KEY-VALUE STORE INITIALIZATION
# --------------------------------------------------

# Shared in-memory store for all request threads.
store = KeyValueStore()

# Restore previously saved data during startup.
store.restore(load_snapshot())

# Initialize asynchronous operation logging.
operation_logger = configure_operation_logger()


# --------------------------------------------------
# HEALTH CHECK ENDPOINT
# --------------------------------------------------

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "success",
        "message": "Key-Value Store Server is Running",
    }), 200


# --------------------------------------------------
# GET OPERATION
# --------------------------------------------------

@app.route("/<key>", methods=["GET"])
def get_value(key):
    try:
        # Retrieve the value from storage.
        value = store.get(key)

    except KeyError:
        # Record unsuccessful GET requests.
        operation_logger.info(
            "GET key=%s status=404",
            key
        )

        return jsonify({
            "error": "Key not found",
            "key": key,
        }), 404

    # Record successful GET requests.
    operation_logger.info(
        "GET key=%s status=200",
        key
    )

    return jsonify({
        "key": key,
        "value": value,
    }), 200


# --------------------------------------------------
# POST / PUT OPERATION
# --------------------------------------------------

@app.route("/<key>", methods=["POST", "PUT"])
def put_value(key):

    # The professor's benchmark uses HTTP POST
    # to perform a key-value write operation.
    data = request.get_json(silent=True)

    # Validate the incoming JSON request.
    if not isinstance(data, dict) or "value" not in data:

        operation_logger.info(
            "PUT method=%s key=%s status=400",
            request.method,
            key
        )

        return jsonify({
            "error": "JSON body must contain a 'value' field",
        }), 400

    # Insert or update the key-value pair.
    is_new = store.put(key, data["value"])

    # Return 201 for new keys and 200 for updates.
    status_code = 201 if is_new else 200

    # Record the write operation.
    operation_logger.info(
        "PUT method=%s key=%s status=%d",
        request.method,
        key,
        status_code
    )

    return jsonify({
        "message": "Key created" if is_new else "Key updated",
        "key": key,
    }), status_code


# --------------------------------------------------
# DELETE OPERATION
# --------------------------------------------------

@app.route("/<key>", methods=["DELETE"])
def delete_value(key):
    try:
        # Remove the key-value pair.
        store.delete(key)

    except KeyError:
        # Record attempts to delete missing keys.
        operation_logger.info(
            "DELETE key=%s status=404",
            key
        )

        return jsonify({
            "error": "Key not found",
            "key": key,
        }), 404

    # Record successful deletion.
    operation_logger.info(
        "DELETE key=%s status=200",
        key
    )

    return jsonify({
        "message": "Key deleted successfully",
        "key": key,
    }), 200


# --------------------------------------------------
# SERVER STARTUP AND BACKGROUND PERSISTENCE
# --------------------------------------------------

if __name__ == "__main__":

    # Event used to stop the persistence worker.
    snapshot_stop_event = Event()

    # Background thread for periodic snapshots.
    snapshot_thread = Thread(
        target=periodic_snapshot_worker,
        args=(store, snapshot_stop_event),
        kwargs={"interval_seconds": 10},
        name="snapshot-worker",
        daemon=True,
    )

    # Start the persistence worker.
    snapshot_thread.start()

    print("Starting Single-Server Key-Value Store")
    print(f"Server listening on: {SERVER_HOST}:{SERVER_PORT}")
    print("Threaded mode: Enabled")
    print("Background persistence: Enabled")
    print("Snapshot interval: 10 seconds")
    print("Asynchronous operation logging: Enabled")
    print("Werkzeug routine access logging: Disabled")

    # --------------------------------------------------
    # START FLASK SERVER
    # --------------------------------------------------

    try:
        app.run(
            host=SERVER_HOST,
            port=SERVER_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    # --------------------------------------------------
    # GRACEFUL SHUTDOWN
    # --------------------------------------------------

    finally:
        print("\nShutting down Key-Value Store...")

        # Stop the background snapshot worker.
        snapshot_stop_event.set()

        # Wait for the worker to finish.
        snapshot_thread.join()

        # Save the final consistent snapshot.
        try:
            save_snapshot(store.snapshot())

            print(
                "Final snapshot saved successfully."
            )

        except Exception:
            operation_logger.exception(
                "Failed to save final snapshot"
            )
            raise
