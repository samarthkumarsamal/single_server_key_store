# Single-Server Key-Value Store

A lightweight key-value store built with Python and Flask for **Cloud Computing — Coding Assignment 1**.

The server allows clients to create, retrieve, update, and delete key-value pairs through HTTP requests. Data is stored in memory for fast access, while thread synchronization, operation logging, and periodic snapshots provide safe concurrent access and basic data recovery.

## 1. Features

- **Key-value operations:** Supports GET, POST, PUT, and DELETE requests.
- **Concurrent request handling:** Handles multiple clients using Flask's threaded server.
- **Thread-safe storage:** Uses a lock to protect the shared dictionary.
- **Data persistence:** Saves snapshots every 10 seconds and restores data when the server restarts.
- **Operation logging:** Records requests, keys, timestamps, and HTTP status codes.
- **Performance testing:** Measures throughput and latency under concurrent workloads.

## 2. Technologies Used

| Technology | Purpose |
|---|---|
| Python | Application and storage implementation |
| Flask | HTTP server and API endpoints |
| Threading | Concurrency control and background tasks |
| Requests | HTTP benchmarking and testing |
| JSON | Request data, responses, and persistent snapshots |

## 3. Project Structure

```text
single-server-kv-store/
├── app/
│   ├── server.py
│   ├── kv_store.py
│   ├── logger.py
│   └── persistence.py
├── benchmarks/
│   ├── provided_benchmark.py
│   ├── corrected_benchmark.py
│   └── get_hit_benchmark.py
├── tests/
│   ├── test_concurrent_put.py
│   ├── test_concurrent_delete.py
│   └── test_mixed_concurrency.py
├── data/
├── logs/
└── README.md
```

The `app` directory contains the server implementation. The `benchmarks` directory contains scripts for measuring performance, and the `tests` directory contains concurrency tests.

The `data` and `logs` directories store generated snapshots and operation logs.

## 4. Installation and Setup

### Prerequisites

- Python 3
- pip
- Windows Command Prompt or a VS Code terminal

### Create and activate a virtual environment

Open a terminal in the project directory:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

If a virtual environment already exists, simply activate it.

### Install dependencies

```cmd
pip install flask requests
```

### Start the server

```cmd
python app/server.py
```

The server runs at:

**http://127.0.0.1:8080**

Keep this terminal open while sending requests or running tests.

## 5. API Endpoints

The application exposes the following HTTP endpoints:

| Method | Endpoint | Description | Response |
|---|---|---|---|
| GET | `/` | Check server availability | 200 |
| GET | `/<key>` | Retrieve a stored value | 200 or 404 |
| POST | `/<key>` | Create or update a key | 201 or 200 |
| PUT | `/<key>` | Create or update a key | 201 or 200 |
| DELETE | `/<key>` | Delete an existing key | 200 or 404 |

For POST and PUT, the request body must be valid JSON containing a `value` field. Invalid input returns HTTP 400.

### Create a key

```cmd
curl -X POST http://127.0.0.1:8080/course -H "Content-Type: application/json" -d "{\"value\":\"Cloud Computing\"}"
```

A new key returns HTTP 201. If the key already exists, its value is updated and the server returns HTTP 200.

### Retrieve a key

```cmd
curl http://127.0.0.1:8080/course
```

Example response:

```json
{
  "key": "course",
  "value": "Cloud Computing"
}
```

If the key does not exist, the server returns HTTP 404.

### Update a key

```cmd
curl -X PUT http://127.0.0.1:8080/course -H "Content-Type: application/json" -d "{\"value\":\"Distributed Systems\"}"
```

### Delete a key

```cmd
curl -X DELETE http://127.0.0.1:8080/course
```

A successful deletion returns HTTP 200. Deleting a missing key returns HTTP 404.

## 6. Implementation Details

### In-Memory Storage

The `KeyValueStore` class in `app/kv_store.py` uses a Python dictionary to store key-value pairs.

Dictionary operations provide efficient key lookup, insertion, and deletion. A shared lock protects the dictionary so concurrent requests cannot access or modify it in an unsafe manner.

The class implements methods for retrieving, inserting, updating, deleting, and snapshotting stored data.

### Concurrent Request Handling

The server runs Flask in threaded mode, allowing multiple HTTP requests to be processed concurrently.

Because all request threads share the same key-value store, synchronization is necessary. The storage lock ensures that individual operations on the dictionary execute safely, even when multiple clients access the same key.

### Asynchronous Logging

The application records operations using a queue-based logging system implemented in `app/logger.py`.

Request threads submit log messages to a queue, and a background listener writes those messages to `logs/operations.log`.

Each record includes information such as the operation type, key, HTTP status, and timestamp.

Routine Werkzeug access messages are disabled to reduce console output during benchmarking. Application operation logging remains enabled.

### Persistence and Recovery

The persistence module saves the in-memory dictionary as a JSON snapshot every 10 seconds.

Snapshots are written to a temporary file before replacing the existing snapshot, helping avoid partially written snapshot files.

When the server starts, it restores data from the latest available snapshot. During a graceful shutdown, it also attempts to save the current state.

Because persistence is periodic rather than performed after every request, an unexpected crash may cause changes made after the latest snapshot to be lost.

## 7. Testing

The implementation includes three concurrency tests.

| Test | Purpose | Result |
|---|---|---|
| Concurrent PUT | Tests multiple writes to the same key | Passed |
| Concurrent DELETE | Tests simultaneous deletion attempts | Passed |
| Mixed concurrency | Tests concurrent GET, PUT, and DELETE requests | Passed |

Run the tests from the project root while the server is running:

```cmd
python tests/test_concurrent_put.py
python tests/test_concurrent_delete.py
python tests/test_mixed_concurrency.py
```

All three tests passed during final verification.

Python syntax was also checked using:

```cmd
python -m compileall -q app benchmarks tests
```

## 8. Performance Benchmarking

The project includes the professor's original benchmark and two additional benchmarks.

### Professor's Original Benchmark

```cmd
python benchmarks/provided_benchmark.py
```

Recorded results:

| Metric | Result |
|---|---:|
| Client threads | 3 |
| Actual HTTP requests | 300 |
| Reported operations | 600 |
| Execution time | 0.46 seconds |
| Reported throughput | 1,294.53 operations/sec |
| Approximate actual throughput | 647 requests/sec |
| Reported average latency | 4.66 ms |

The original script reports 600 operations even though it sends 300 HTTP requests. Consequently, the reported throughput is approximately twice the actual HTTP request throughput.

Its latency calculation also does not include every request.

### Corrected Mixed-Workload Benchmark

```cmd
python benchmarks/corrected_benchmark.py
```

This benchmark measures every attempted HTTP request, including responses with HTTP 404.

It uses three client threads, with 1,000 requests per thread.

Average results across three runs:

| Metric | Result |
|---|---:|
| Total requests per run | 3,000 |
| Average throughput | 261.94 requests/sec |
| Average latency | 11.447 ms |
| P95 latency | 27.404 ms |
| P99 latency | 29.679 ms |
| Unexpected failures | 0 |

The workload consists of 50% POST requests that create keys and 50% GET requests targeting nonexistent keys. HTTP 404 is the expected result for those GET requests.

### Successful GET Benchmark

```cmd
python benchmarks/get_hit_benchmark.py
```

This test measures the server's performance when retrieving a key that already exists.

Average results across three 3,000-request runs:

| Metric | Result |
|---|---:|
| Client threads | 3 |
| Total requests per run | 3,000 |
| Average throughput | 270.45 requests/sec |
| Average latency | 10.930 ms |
| P95 latency | 26.979 ms |
| P99 latency | 28.952 ms |
| Failed requests | 0 |

These benchmarks measure different workloads, so their results should not be interpreted as a direct comparison of server optimizations.

## 9. Limitations

This implementation is designed for a single server rather than a distributed environment.

- Data is maintained in one server process, without replication.
- Persistence uses periodic snapshots rather than saving after every update.
- The API does not implement authentication.
- Flask's built-in development server is intended for local testing rather than production deployment.
- Network access is restricted to the local machine through `127.0.0.1`.

## 10. Summary

The project implements a working single-server key-value store with REST-style HTTP operations, thread-safe access, asynchronous logging, and periodic persistence.

Functional and concurrency tests passed, and benchmark measurements were collected using the professor's original workload and additional tests.

The implementation meets the core objectives of the assignment while providing basic persistence and performance-measurement capabilities.
