import asyncio
import json
import logging
import os
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from queue import SimpleQueue

from aiohttp import web


# ============================================================
# Server configuration
# ============================================================

# Store persistent data and operation logs in configurable paths.
DATA_FILE = Path(os.getenv("KV_DATA_FILE", "kv_data.json"))
LOG_FILE = Path(os.getenv("KV_LOG_FILE", "kv_operations.log"))

# Save modified records periodically rather than writing on every request.
SAVE_INTERVAL = float(os.getenv("KV_SAVE_INTERVAL", "2"))
PORT = int(os.getenv("PORT", "8080"))


# ============================================================
# Shared key-value state and background services
# ============================================================

class KVState:
    """Manage in-memory records, asynchronous persistence, and logging."""

    def __init__(self):
        # Restore persisted records before accepting HTTP requests.
        self.store = self._load_data()

        # Revisions ensure that a completed snapshot is not confused with
        # writes that arrived while that snapshot was being saved.
        self.revision = 0
        self.saved_revision = 0
        self.save_lock = asyncio.Lock()
        self.stop_event = asyncio.Event()
        self.save_task = None

        # A background listener performs file logging outside the event loop.
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.file_handler = logging.FileHandler(
            LOG_FILE, mode="a", encoding="utf-8"
        )
        self.file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )

        log_queue = SimpleQueue()
        self.queue_handler = QueueHandler(log_queue)
        self.log_listener = QueueListener(log_queue, self.file_handler)

        # Keep operation logs separate from the root and aiohttp loggers.
        self.logger = logging.getLogger(f"kv-store-{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.addHandler(self.queue_handler)

    @staticmethod
    def _load_data():
        """Load the last complete JSON snapshot, if one exists."""
        if not DATA_FILE.exists():
            return {}

        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("KV data file must contain a JSON object")

        return data

    @staticmethod
    def _write_snapshot(snapshot):
        """Write and atomically publish a snapshot in a worker thread."""
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = DATA_FILE.with_name(DATA_FILE.name + ".tmp")

        # Write to a temporary file so readers never see partial JSON.
        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(snapshot, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())

        # Replace the previous complete snapshot only after the write succeeds.
        os.replace(temp_file, DATA_FILE)

    async def save_if_dirty(self):
        """Persist new revisions without blocking incoming HTTP requests."""
        async with self.save_lock:
            if self.revision == self.saved_revision:
                return

            # Capture a consistent copy before transferring work to a thread.
            snapshot = self.store.copy()
            revision = self.revision

            # Keep a handle to the worker so cancellation cannot leave a
            # background disk write running unobserved during shutdown.
            write_task = asyncio.create_task(
                asyncio.to_thread(self._write_snapshot, snapshot)
            )

            try:
                await asyncio.shield(write_task)
            except asyncio.CancelledError:
                # Wait until an already-started write has finished before
                # allowing cancellation to propagate to the caller.
                await write_task
                raise

            # If requests modified the store during the write, those edits
            # have a newer revision and will be included in a later snapshot.
            self.saved_revision = revision

    async def save_periodically(self):
        """Save changed data at intervals and once more on shutdown."""
        while not self.stop_event.is_set():
            try:
                # This wait wakes immediately when shutdown is requested.
                await asyncio.wait_for(
                    self.stop_event.wait(), timeout=SAVE_INTERVAL
                )
            except asyncio.TimeoutError:
                try:
                    await self.save_if_dirty()
                except Exception:
                    # Keep serving requests if an individual snapshot fails.
                    self.logger.exception("Periodic data snapshot failed")

        # Include any updates that arrived after the last periodic snapshot.
        await self.save_if_dirty()


# ============================================================
# HTTP handlers
# ============================================================

async def get_key(request):
    """Return the JSON value associated with a key."""
    state = request.app["kv_state"]
    key = request.match_info["key"]

    if key not in state.store:
        state.logger.info("GET key=%s status=404", key)
        return web.json_response({"error": "Key not found"}, status=404)

    state.logger.info("GET key=%s status=200", key)
    return web.json_response({"value": state.store[key]}, status=200)


async def set_key(request):
    """Create or replace a record using POST or PUT."""
    state = request.app["kv_state"]
    key = request.match_info["key"]

    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        state.logger.info("%s key=%s status=400", request.method, key)
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    if not isinstance(body, dict) or "value" not in body:
        state.logger.info("%s key=%s status=400", request.method, key)
        return web.json_response(
            {"error": "JSON body must contain a 'value' field"},
            status=400,
        )

    # The in-memory update is immediate; the snapshot task handles disk I/O.
    state.store[key] = body["value"]
    state.revision += 1
    state.logger.info("%s key=%s status=200", request.method, key)
    return web.json_response({"value": body["value"]}, status=200)


async def delete_key(request):
    """Delete a record and schedule persistence of the change."""
    state = request.app["kv_state"]
    key = request.match_info["key"]

    if key not in state.store:
        state.logger.info("DELETE key=%s status=404", key)
        return web.json_response({"error": "Key not found"}, status=404)

    del state.store[key]
    state.revision += 1
    state.logger.info("DELETE key=%s status=200", key)
    return web.json_response({"message": "Key deleted"}, status=200)


async def list_keys(request):
    """List local keys for monitoring and controlled migrations."""
    state = request.app["kv_state"]
    return web.json_response({"keys": list(state.store.keys())})


# ============================================================
# Application lifecycle
# ============================================================

async def on_startup(app):
    """Start queued logging and the periodic snapshot task."""
    state = app["kv_state"]
    state.log_listener.start()
    state.logger.info("Server started with %d keys", len(state.store))
    state.save_task = asyncio.create_task(state.save_periodically())


async def on_cleanup(app):
    """Flush pending data and logs before releasing resources."""
    state = app["kv_state"]
    state.stop_event.set()

    try:
        if state.save_task is not None:
            await state.save_task
    finally:
        state.logger.info("Server stopped")
        state.log_listener.stop()
        state.logger.removeHandler(state.queue_handler)
        state.file_handler.close()


def create_app():
    """Configure the REST API, state, and lifecycle callbacks."""
    if SAVE_INTERVAL <= 0:
        raise ValueError("KV_SAVE_INTERVAL must be greater than zero")

    app = web.Application()
    app["kv_state"] = KVState()

    # Register the administrative endpoint before the generic key routes.
    app.router.add_get("/_admin/keys", list_keys)
    app.router.add_get("/{key}", get_key)
    app.router.add_post("/{key}", set_key)
    app.router.add_put("/{key}", set_key)
    app.router.add_delete("/{key}", delete_key)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
