import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4


BASE_URL = "http://127.0.0.1:8080"
NUM_THREADS = 10

# Generate a unique key for each test
TEST_KEY = f"delete-test-{uuid4().hex}"

# Synchronize all DELETE requests
start_barrier = Barrier(NUM_THREADS)


def create_test_key():
    """
    Create a key before concurrent deletion.
    """
    payload = json.dumps({
        "value": "cloud-computing"
    }).encode("utf-8")

    request = Request(
        f"{BASE_URL}/{TEST_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urlopen(request, timeout=10) as response:
        assert response.status == 201


def concurrent_delete(thread_id):
    """
    Attempt to delete the same key concurrently.
    """
    request = Request(
        f"{BASE_URL}/{TEST_KEY}",
        method="DELETE"
    )

    # Start all threads at approximately the same time
    start_barrier.wait()

    try:
        with urlopen(request, timeout=10) as response:
            return response.status

    except HTTPError as error:
        return error.code


def test_concurrent_delete():
    print("Starting concurrent DELETE test...")

    # Create the key before testing
    create_test_key()

    # Execute 10 concurrent DELETE requests
    with ThreadPoolExecutor(
        max_workers=NUM_THREADS
    ) as executor:
        statuses = list(
            executor.map(
                concurrent_delete,
                range(NUM_THREADS)
            )
        )

    successful = statuses.count(200)
    not_found = statuses.count(404)

    print(f"Total concurrent requests: {NUM_THREADS}")
    print(f"Successful deletions: {successful}")
    print(f"Key not found responses: {not_found}")

    # Verify concurrent deletion behavior
    assert successful == 1
    assert not_found == NUM_THREADS - 1

    # Confirm key no longer exists
    request = Request(
        f"{BASE_URL}/{TEST_KEY}",
        method="GET"
    )

    try:
        with urlopen(request, timeout=10):
            raise AssertionError(
                "Deleted key still exists!"
            )

    except HTTPError as error:
        assert error.code == 404

    print("Final key verification: 404 Not Found")
    print("PASS: Concurrent DELETE test successful!")


if __name__ == "__main__":
    test_concurrent_delete()
