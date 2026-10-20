import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.request import Request, urlopen
from uuid import uuid4


BASE_URL = "http://127.0.0.1:8080"
NUM_THREADS = 10

# Use a unique key for each test run
TEST_KEY = f"concurrent-test-{uuid4().hex}"

# Synchronize concurrent requests
start_barrier = Barrier(NUM_THREADS)


def concurrent_put(thread_id):
    """
    Send a POST request to the same key.
    """

    payload = json.dumps({
        "value": f"value-{thread_id}"
    }).encode("utf-8")

    request = Request(
        f"{BASE_URL}/{TEST_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start_barrier.wait()

    with urlopen(request, timeout=10) as response:
        return response.status


def test_concurrent_put():
    print("Starting concurrent PUT test...")

    with ThreadPoolExecutor(
        max_workers=NUM_THREADS
    ) as executor:
        statuses = list(
            executor.map(
                concurrent_put,
                range(NUM_THREADS)
            )
        )

    created = statuses.count(201)
    updated = statuses.count(200)

    # Retrieve final stored value
    with urlopen(
        f"{BASE_URL}/{TEST_KEY}",
        timeout=10
    ) as response:
        result = json.load(response)

    possible_values = {
        f"value-{i}" for i in range(NUM_THREADS)
    }

    print(f"Total concurrent requests: {NUM_THREADS}")
    print(f"Created responses: {created}")
    print(f"Updated responses: {updated}")
    print(f"Final stored value: {result['value']}")

    assert created == 1
    assert updated == NUM_THREADS - 1
    assert result["value"] in possible_values

    print("PASS: Concurrent PUT test successful!")


if __name__ == "__main__":
    test_concurrent_put()
