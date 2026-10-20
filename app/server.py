import logging
from threading import Event, Thread

from flask import Flask, jsonify, request

from kv_store import KeyValueStore
from logger import configure_operation_logger
from persistence import (
    load_snapshot,
    periodic_snapshot_worker,
    save_snapshot,
)


# Initialize Flask application.
app = Flask(__name__)

# Suppress routine Werkzeug console access logs while keeping errors visible.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# One shared in-memory store for all Flask request threads.
store = KeyValueStore()

# Restore the latest available snapshot before accepting requests.
store.restore(load_snapshot())

# Set up asynchronous operation logging.
operation_logger = configure_operation_logger()


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "success",
        "message": "Key-Value Store Server is Running",
    }), 200


@app.route("/<key>", methods=["GET"])
def get_value(key):
    try:
        value = store.get(key)
    except KeyError:
        operation_logger.info("GET key=%s status=404", key)
        return jsonify({
            "error": "Key not found",
            "key": key,
        }), 404

    operation_logger.info("GET key=%s status=200", key)
    return jsonify({
        "key": key,
        "value": value,
    }), 200


@app.route("/<key>", methods=["POST", "PUT"])
def put_value(key):
    # The professor's benchmark uses HTTP POST to perform a PUT operation.
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "value" not in data:
        operation_logger.info(
            "PUT method=%s key=%s status=400", request.method, key
        )
        return jsonify({
            "error": "JSON body must contain a 'value' field",
        }), 400

    is_new = store.put(key, data["value"])
    status_code = 201 if is_new else 200

    operation_logger.info(
        "PUT method=%s key=%s status=%d", request.method, key, status_code
    )
    return jsonify({
        "message": "Key created" if is_new else "Key updated",
        "key": key,
    }), status_code


@app.route("/<key>", methods=["DELETE"])
def delete_value(key):
    try:
        store.delete(key)
    except KeyError:
        operation_logger.info("DELETE key=%s status=404", key)
        return jsonify({
            "error": "Key not found",
            "key": key,
        }), 404

    operation_logger.info("DELETE key=%s status=200", key)
    return jsonify({
        "message": "Key deleted successfully",
        "key": key,
    }), 200


if __name__ == "__main__":
    snapshot_stop_event = Event()
    snapshot_thread = Thread(
        target=periodic_snapshot_worker,
        args=(store, snapshot_stop_event),
        kwargs={"interval_seconds": 10},
        name="snapshot-worker",
        daemon=True,
    )
    snapshot_thread.start()

    print("Starting Single-Server Key-Value Store")
    print("Server URL: http://127.0.0.1:8080")
    print("Threaded mode: Enabled")
    print("Background persistence: Enabled (10-second interval)")
    print("Asynchronous operation logging: Enabled")
    print("Werkzeug routine access logging: Disabled")

    try:
        app.run(
            host="127.0.0.1",
            port=8080,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    finally:
        print("\nShutting down Key-Value Store...")
        snapshot_stop_event.set()
        snapshot_thread.join()

        try:
            save_snapshot(store.snapshot())
            print("Final snapshot saved successfully.")
        except Exception:
            operation_logger.exception("Failed to save final snapshot")
            raise
