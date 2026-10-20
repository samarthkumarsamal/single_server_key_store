import math
import threading
import time
import uuid
from collections import Counter
from queue import Empty, Queue
from statistics import mean

import requests


# Match the professor's mix and concurrency; use more operations for stability.
BASE_URL = "http://127.0.0.1:8080"
NUM_THREADS = 3
OPS_PER_THREAD = 1000
TOTAL_REQUESTS = NUM_THREADS * OPS_PER_THREAD
REQUEST_TIMEOUT = 10
RUN_ID = uuid.uuid4().hex[:10]

operations_queue = Queue()
results_queue = Queue()
start_barrier = threading.Barrier(NUM_THREADS + 1)


def percentile(values, percentage):
    """Nearest-rank percentile."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = math.ceil(percentage / 100 * len(ordered))
    return ordered[max(0, rank - 1)]


def prepare_operations():
    """Create alternating writes and missing-key reads."""
    for i in range(TOTAL_REQUESTS):
        operation = "get" if i % 2 else "set"
        key = f"bench_{RUN_ID}_key_{i}"
        value = f"value_{i}" if operation == "set" else None
        operations_queue.put((operation, key, value))


def worker_thread():
    start_barrier.wait()

    while True:
        try:
            operation, key, value = operations_queue.get_nowait()
        except Empty:
            break

        start_time = time.perf_counter()
        status_code = None

        try:
            if operation == "set":
                response = requests.post(
                    f"{BASE_URL}/{key}",
                    json={"value": value},
                    timeout=REQUEST_TIMEOUT,
                )
            else:
                response = requests.get(
                    f"{BASE_URL}/{key}",
                    timeout=REQUEST_TIMEOUT,
                )
            status_code = response.status_code
        except requests.RequestException:
            pass

        elapsed = time.perf_counter() - start_time
        results_queue.put((operation, status_code, elapsed))


def run_benchmark():
    print("\nStarting Corrected Benchmark")
    print("-" * 45)
    print(f"Client threads: {NUM_THREADS}")
    print(f"Requests per thread: {OPS_PER_THREAD}")
    print(f"Total requests: {TOTAL_REQUESTS}")

    prepare_operations()

    threads = [threading.Thread(target=worker_thread) for _ in range(NUM_THREADS)]
    for thread in threads:
        thread.start()

    benchmark_start = time.perf_counter()
    start_barrier.wait()
    for thread in threads:
        thread.join()
    total_time = time.perf_counter() - benchmark_start

    results = []
    while True:
        try:
            results.append(results_queue.get_nowait())
        except Empty:
            break

    completed = len(results)
    latencies_ms = [latency * 1000 for _, _, latency in results]
    status_counts = Counter(
        status for _, status, _ in results if status is not None
    )
    successful = sum(
        count for status, count in status_counts.items() if 200 <= status < 300
    )
    expected_404 = status_counts.get(404, 0)
    network_errors = sum(status is None for _, status, _ in results)
    other_http_errors = (
        completed - successful - expected_404 - network_errors
    )
    throughput = completed / total_time if total_time > 0 else 0

    print("\n" + "=" * 45)
    print("CORRECTED BENCHMARK RESULTS")
    print("=" * 45)
    print(f"Total requests: {completed}")
    print(f"Total time: {total_time:.4f} seconds")
    print(f"Throughput: {throughput:.2f} requests/sec")
    print(f"Average latency: {mean(latencies_ms):.3f} ms")
    print(f"P50 latency: {percentile(latencies_ms, 50):.3f} ms")
    print(f"P95 latency: {percentile(latencies_ms, 95):.3f} ms")
    print(f"P99 latency: {percentile(latencies_ms, 99):.3f} ms")

    print("\nHTTP Response Summary:")
    for status, count in sorted(status_counts.items()):
        print(f"HTTP {status}: {count}")
    print(f"\nSuccessful HTTP requests: {successful}")
    print(f"Expected 404 responses: {expected_404}")
    print(f"Other HTTP errors: {other_http_errors}")
    print(f"Network failures: {network_errors}")

    print("\n" + "=" * 45)
    print("PER-OPERATION LATENCY ANALYSIS")
    print("=" * 45)

    for operation in ("set", "get"):
        operation_results = [
            (status, latency * 1000)
            for op, status, latency in results
            if op == operation
        ]
        operation_latencies = [latency for _, latency in operation_results]
        operation_name = "PUT" if operation == "set" else "GET"
        print(f"\n{operation_name} Operation:")
        print(f"Requests: {len(operation_latencies)}")
        print(f"Average latency: {mean(operation_latencies):.3f} ms")
        print(f"P50 latency: {percentile(operation_latencies, 50):.3f} ms")
        print(f"P95 latency: {percentile(operation_latencies, 95):.3f} ms")
        print(f"P99 latency: {percentile(operation_latencies, 99):.3f} ms")

        operation_statuses = Counter(status for status, _ in operation_results)
        print("Response counts:")
        for status, count in sorted(
            operation_statuses.items(),
            key=lambda item: (item[0] is None, item[0] or 0),
        ):
            label = "Network Error" if status is None else f"HTTP {status}"
            print(f"  {label}: {count}")

    assert completed == TOTAL_REQUESTS, "Not all requests were measured"
    assert network_errors == 0, "Network failures occurred"
    assert other_http_errors == 0, "Unexpected HTTP errors occurred"

    # Verify that the professor's specific mixed workload behaved correctly.
    status_by_operation = Counter((op, status) for op, status, _ in results)
    assert status_by_operation[("set", 201)] == TOTAL_REQUESTS // 2
    assert status_by_operation[("get", 404)] == TOTAL_REQUESTS // 2
    print("\nBenchmark completed successfully.")


if __name__ == "__main__":
    run_benchmark()
