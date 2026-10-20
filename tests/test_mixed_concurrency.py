import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4


BASE_URL = "http://127.0.0.1:8080"
NUM_PER_OPERATION = 5
TOTAL_REQUESTS = NUM_PER_OPERATION * 3

TEST_KEY = f"mixed-test-{uuid4().hex}"

# Synchronize concurrent requests
start_barrier = Barrier(TOTAL_REQUESTS)


def send_request(method, value=None):
    url = f"{BASE_URL}/{TEST_KEY}"

    if method == "POST":
        payload = json.dumps({
            "value": value
        }).encode("utf-8")

        request = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
    else:
        request = Request(url, method=method)

    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)

    except HTTPError as error:
        return error.code, json.load(error)


def worker(task):
    operation, index = task

    # Start concurrent operations together
    start_barrier.wait(timeout=10)

    if operation == "PUT":
        status, body = send_request(
            "POST", f"value-{index}"
        )
    else:
        status, body = send_request(operation)

    return operation, status, body


def test_mixed_concurrency():
    print("Starting mixed concurrency test...")

    # Create the initial key
    status, _ = send_request(
        "POST", "initial-value"
    )
    assert status == 201

    # Prepare mixed operations
    tasks = []

    for i in range(NUM_PER_OPERATION):
        tasks.append(("GET", i))
        tasks.append(("PUT", i))
        tasks.append(("DELETE", i))

    # Execute requests concurrently
    with ThreadPoolExecutor(
        max_workers=TOTAL_REQUESTS
    ) as executor:
        results = list(executor.map(worker, tasks))

    valid_values = {"initial-value"} | {
        f"value-{i}" for i in range(NUM_PER_OPERATION)
    }

    # Validate every response
    for operation, status, body in results:
        if operation == "GET":
            assert status in (200, 404)

            if status == 200:
                assert body["key"] == TEST_KEY
                assert body["value"] in valid_values
            else:
                assert body["error"] == "Key not found"

        elif operation == "PUT":
            assert status in (200, 201)
            assert body["key"] == TEST_KEY

        elif operation == "DELETE":
            assert status in (200, 404)
            assert body["key"] == TEST_KEY

    # Display operation statistics
    counts = Counter(
        (operation, status)
        for operation, status, _ in results
    )

    print(f"Total requests: {len(results)}")

    for (operation, status), count in sorted(counts.items()):
        print(f"{operation} HTTP {status}: {count}")

    # Verify final store state
    final_status, final_body = send_request("GET")

    assert final_status in (200, 404)

    if final_status == 200:
        assert final_body["value"] in valid_values
        print("Final state: Key exists with valid value")
    else:
        print("Final state: Key deleted")

    print("PASS: Mixed concurrency test successful!")


if __name__ == "__main__":
    test_mixed_concurrency()
