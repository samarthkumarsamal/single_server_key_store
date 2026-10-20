import math
import threading
import time
import uuid
from statistics import mean

import requests


BASE_URL = "http://127.0.0.1:8080"
NUM_THREADS = 3
OPS_PER_THREAD = 1000
TOTAL_REQUESTS = NUM_THREADS * OPS_PER_THREAD
REQUEST_TIMEOUT = 10

TEST_KEY = f"get_hit_{uuid.uuid4().hex}"
start_barrier = threading.Barrier(NUM_THREADS + 1)
results = [[] for _ in range(NUM_THREADS)]


def percentile(values, percent):
    """Calculate the nearest-rank percentile."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = math.ceil(len(ordered) * percent / 100)
    return ordered[max(0, rank - 1)]


def worker(thread_id):
    """Measure successful GET requests for a pre-created key."""
    local_results = []
    start_barrier.wait()

    for _ in range(OPS_PER_THREAD):
        start = time.perf_counter()
        try:
            response = requests.get(
                f"{BASE_URL}/{TEST_KEY}",
                timeout=REQUEST_TIMEOUT,
            )
            status = response.status_code
        except requests.RequestException:
            status = None

        latency_ms = (time.perf_counter() - start) * 1000
        local_results.append((status, latency_ms))

    results[thread_id] = local_results


def run_benchmark():
    print("Starting Successful GET Benchmark")

    # Setup request is excluded from the timed GET workload.
    response = requests.post(
        f"{BASE_URL}/{TEST_KEY}",
        json={"value": "benchmark-value"},
        timeout=REQUEST_TIMEOUT,
    )
    assert response.status_code == 201, "Failed to initialize test key"

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(NUM_THREADS)
    ]
    for thread in threads:
        thread.start()

    start = time.perf_counter()
    start_barrier.wait()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - start

    all_results = [
        item for thread_results in results for item in thread_results
    ]
    latencies = [latency for _, latency in all_results]
    successful = sum(status == 200 for status, _ in all_results)
    failed = len(all_results) - successful
    throughput = len(all_results) / elapsed

    print("\n" + "=" * 45)
    print("SUCCESSFUL GET BENCHMARK RESULTS")
    print("=" * 45)
    print(f"Threads: {NUM_THREADS}")
    print(f"Total requests: {len(all_results)}")
    print(f"Total time: {elapsed:.4f} seconds")
    print(f"Throughput: {throughput:.2f} requests/sec")
    print(f"Average latency: {mean(latencies):.3f} ms")
    print(f"P50 latency: {percentile(latencies, 50):.3f} ms")
    print(f"P95 latency: {percentile(latencies, 95):.3f} ms")
    print(f"P99 latency: {percentile(latencies, 99):.3f} ms")
    print(f"Successful GET requests: {successful}")
    print(f"Failed requests: {failed}")

    assert len(all_results) == TOTAL_REQUESTS
    assert failed == 0
    print("\nPASS: Successful GET benchmark completed!")


if __name__ == "__main__":
    run_benchmark()
