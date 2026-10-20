# Single-Server Key-Value Store

**Cloud Computing — Coding Assignments 1 and 2**  
**Student:** Samarth Kumar Samal  
**Technologies:** Python 3.13, Flask, Docker, Threading, JSON, Requests

## 1. Project Overview

This project implements a single-server key-value store that clients can access through a REST-style HTTP API. It supports creating, reading, updating, and deleting key-value pairs, while protecting shared data from concurrent access.

The project was completed in two stages:

| Assignment | Scope |
|---|---|
| **Assignment 1 — Key-Value Store** | Build and test a threaded Flask server with in-memory storage, logging, persistence, and performance benchmarks. |
| **Assignment 2 — Dockerization** | Package the same application in a lightweight Linux container, expose port 8080, and verify API functionality, concurrency, and data recovery. |

Both versions use the same application code. Docker changes how the application is packaged and run; it does not replace the storage implementation.

## 2. Features

- **REST API:** GET, POST, PUT, and DELETE operations on individual keys.
- **Thread-safe storage:** A shared Python dictionary protected by `threading.Lock`.
- **Concurrent clients:** Flask handles multiple requests using threaded mode.
- **Asynchronous logging:** Timestamped operation records are written to `logs/operations.log` through a logging queue.
- **Persistence:** JSON snapshots are saved every 10 seconds and restored when the server starts.
- **Performance measurement:** Benchmarks report throughput, average latency, and latency percentiles.
- **Docker deployment:** A Python 3.13 Alpine image runs the server on port 8080 with named volumes for data and logs.

## 3. Project Structure

```text
single-server-kv-store/
├── app/
│   ├── server.py                 # Flask routes and server startup
│   ├── kv_store.py               # Thread-safe key-value storage
│   ├── logger.py                 # Asynchronous operation logging
│   └── persistence.py            # Save and restore JSON snapshots
├── benchmarks/
│   ├── provided_benchmark.py     # Professor's original benchmark
│   ├── corrected_benchmark.py    # Mixed-workload performance test
│   └── get_hit_benchmark.py      # Successful GET performance test
├── tests/
│   ├── test_concurrent_put.py
│   ├── test_concurrent_delete.py
│   └── test_mixed_concurrency.py
├── Dockerfile                    # Docker image instructions
├── .dockerignore                 # Excludes unnecessary build files
├── requirements.txt              # Python dependencies
├── README.md
└── Report.md                     # Assignment report
```

The application creates `data/` and `logs/` at runtime as needed. These directories are not copied into the Docker image; Docker named volumes hold their contents when the container runs.

## 4. Assignment 1 — Running the Application Locally

### Prerequisites

- Python 3.13 (or a compatible Python 3 version)
- pip and a terminal

From the project directory, create a virtual environment, activate it in **Windows Command Prompt**, and install the dependencies:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Start the Flask server:

```cmd
python app/server.py
```

Open **http://127.0.0.1:8080/** to check that it is running. For local execution, Flask listens on `127.0.0.1` by default. Keep the server terminal open while testing.

**Note:** If the Docker container is already using port 8080, stop it with `docker stop cloud-kv-store` before launching the local server.

## 5. API Reference

The same endpoints work for both local execution and Docker deployment.

| HTTP Method | Endpoint | Action | Expected status |
|---|---|---|---|
| GET | `/` | Check server health | 200 |
| GET | `/<key>` | Retrieve an existing key | 200; 404 if missing |
| POST | `/<key>` | Create or update a key | 201 if created; 200 if updated |
| PUT | `/<key>` | Create or update a key | 201 if created; 200 if updated |
| DELETE | `/<key>` | Remove a key | 200; 404 if missing |

POST and PUT require a JSON object containing a `value` field. Invalid input returns HTTP 400.

### API examples (Windows Command Prompt)

**Create a key:**

```cmd
curl -i -X POST http://127.0.0.1:8080/course -H "Content-Type: application/json" -d "{\"value\":\"Cloud Computing\"}"
```

**Retrieve the key:**

```cmd
curl -i http://127.0.0.1:8080/course
```

An existing key returns a response such as:

```json
{"key":"course","value":"Cloud Computing"}
```

**Update the key:**

```cmd
curl -i -X PUT http://127.0.0.1:8080/course -H "Content-Type: application/json" -d "{\"value\":\"Distributed Systems\"}"
```

**Delete the key:**

```cmd
curl -i -X DELETE http://127.0.0.1:8080/course
```

A subsequent GET returns HTTP 404 because the key no longer exists.

## 6. Assignment 1 — Implementation Details

### In-memory storage and concurrency

`app/kv_store.py` implements a `KeyValueStore` backed by a Python dictionary. A shared `threading.Lock` protects each read, write, delete, and snapshot operation. Flask runs in threaded mode, allowing multiple requests to share the same store without corrupting its state.

### Operation logging

`app/logger.py` uses queue-based asynchronous logging. Request handlers enqueue records containing the operation, key, and HTTP status; a background listener writes timestamped records to `logs/operations.log`. Routine Werkzeug access logging is suppressed, while application operation logging remains enabled.

### Persistence and recovery

`app/persistence.py` periodically saves a consistent JSON snapshot. It writes to a temporary file and atomically replaces the previous snapshot to reduce the risk of partial files. The server restores the latest snapshot on startup and attempts a final save during graceful shutdown.

Snapshots occur every **10 seconds**, not after every write. An unexpected shutdown can therefore lose updates made since the most recent snapshot.

## 7. Assignment 2 — Docker Deployment

### Prerequisites

Install Docker Desktop and make sure its **Linux container engine is running**. Verify it with:

```cmd
docker --version
docker info
```

### Docker image configuration

The root-level `Dockerfile` uses **`python:3.13-alpine`**, installs packages from `requirements.txt`, copies the `app/` directory, documents port 8080, and launches `python app/server.py` automatically.

The container sets `HOST=0.0.0.0` so Flask accepts connections through Docker's published port. Outside Docker, the server retains its default `127.0.0.1` address. The `.dockerignore` file excludes virtual environments, caches, generated data, local logs, tests, and documentation from the build context.

### Build the image

From the project root, run:

```cmd
docker build -t cloud-kv-store:1.0 .
```

The final period (`.`) is required: it specifies the current folder as the Docker build context.

### Run the container

Stop any locally running Flask server that occupies port 8080, then run:

```cmd
docker run -d --name cloud-kv-store -p 8080:8080 -v kv-store-data:/app/data -v kv-store-logs:/app/logs cloud-kv-store:1.0
```

| Option | Purpose |
|---|---|
| `-d` | Run in the background |
| `--name cloud-kv-store` | Assign a recognizable container name |
| `-p 8080:8080` | Publish container port 8080 on the host |
| `-v kv-store-data:/app/data` | Persist JSON snapshots outside the container |
| `-v kv-store-logs:/app/logs` | Persist application log files outside the container |

Check the running container and API:

```cmd
docker ps
curl http://127.0.0.1:8080/
```

The health endpoint should return:

```json
{"message":"Key-Value Store Server is Running","status":"success"}
```

### Manage the container

```cmd
docker stop cloud-kv-store
docker start cloud-kv-store
docker restart cloud-kv-store
docker logs cloud-kv-store
```

`docker logs` displays container console output. Detailed operation records are saved separately in `logs/operations.log` within the logs volume.

If you remove the container with `docker rm cloud-kv-store`, recreate it with the same `docker run` command to reconnect the existing named volumes. **Do not remove the volumes** if you want to preserve saved data.

## 8. Testing and Verification

### Concurrency tests

With either the local Flask server or Docker container running on port 8080, execute from the project root:

```cmd
python tests/test_concurrent_put.py
python tests/test_concurrent_delete.py
python tests/test_mixed_concurrency.py
```

| Test | Observed result | Status |
|---|---|---|
| Concurrent PUT | 10 requests: 1 creation, 9 updates | Passed |
| Concurrent DELETE | 10 requests: 1 deletion, 9 missing-key responses | Passed |
| Mixed concurrency | 15 GET/PUT/DELETE requests; consistent final state | Passed |

These three tests passed both during Assignment 1 verification and against the Dockerized application in Assignment 2.

### Docker API and persistence tests

The container passed the health check, POST, GET, PUT, DELETE, and missing-key HTTP 404 tests.

Persistence was verified by creating a key, allowing the periodic snapshot to run, and then retrieving the same value after both a **container restart** and **removal/recreation with the same volumes**:

```json
{"key":"persistence-test","value":"Docker persistence working"}
```

Both recovery checks returned HTTP 200 with the expected value.

## 9. Assignment 1 — Performance Results

The following measurements were collected for the **Assignment 1 server**, not as Docker performance results. Tests used **three client threads**, matching the professor's configuration.

| Benchmark | Throughput | Average latency | Notes |
|---|---:|---:|---|
| Professor's original script | 1,294.53 reported operations/sec | 4.66 ms reported | 0.46-second run; reported operation count is inflated |
| Original script, adjusted request count | Approximately 647 HTTP requests/sec | Not reliably measured for all requests | 300 actual requests, not 600 |
| Corrected mixed-workload benchmark | **261.94 requests/sec** | **11.447 ms** | Mean of 3 runs with 3,000 requests each |
| Successful GET benchmark | **270.45 requests/sec** | **10.930 ms** | Mean of 3 runs with 3,000 successful GETs each |

The corrected mixed-workload benchmark recorded **P95 = 27.404 ms** and **P99 = 29.679 ms**, with no unexpected failures. Its workload contains 50% POST requests and 50% GET requests for missing keys (expected HTTP 404).

**Measurement caveat:** The professor's script reports 600 operations although it sends only 300 HTTP requests, so its throughput is roughly double the actual request rate. Its average latency also excludes some requests. The shorter original test and longer corrected tests are different workloads and should not be treated as a direct performance comparison. No separate containerized throughput benchmark is claimed here.

## 10. Limitations and Conclusion

This is a single-server implementation without replication or authentication. Persistence is periodic, so a sudden shutdown can lose recent changes. Flask's built-in server is appropriate for the assignment and local testing but is not intended as a production deployment server.

**Assignment 1** delivered a functioning, thread-safe key-value store with logging, persistence, concurrency tests, and performance measurements. **Assignment 2** successfully packaged that same application into a Docker image, exposed its API on port 8080, and verified CRUD operations, concurrency, and persistence across container replacement.