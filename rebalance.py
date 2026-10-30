# ============================================================
# 1. IMPORT REQUIRED LIBRARIES
# ============================================================

import argparse
import socket

from collections import defaultdict
from urllib.parse import quote

import requests

from consistent_hash import ConsistentHashRing


# ============================================================
# 2. SERVER CONFIGURATION
# ============================================================

# Map server names to their published localhost ports.
NODE_PORTS = {
    "kv1": 8081,
    "kv2": 8082,
    "kv3": 8083,
}

# Maximum time allowed for each HTTP request.
TIMEOUT = 5


# ============================================================
# 3. VALIDATE SERVER NAMES
# ============================================================

def parse_nodes(text):
    """
    Convert a comma-separated string into a tuple
    of validated server names.
    """

    # Remove whitespace from each supplied name.
    nodes = [
        name.strip()
        for name in text.split(",")
    ]

    # Reject empty names and unsupported servers.
    if not nodes or any(
        name not in NODE_PORTS for name in nodes
    ):
        raise ValueError(
            "Use known nodes: kv1, kv2, kv3"
        )

    # Prevent duplicate physical servers.
    if len(nodes) != len(set(nodes)):
        raise ValueError(
            "Each node must appear only once"
        )

    return tuple(nodes)


# ============================================================
# 4. CONSTRUCT DIRECT SERVER URLS
# ============================================================

def key_url(node, key):
    """
    Construct the HTTP URL for a key on a specific server.
    """

    # Encode special URL characters in the key.
    encoded_key = quote(key, safe="")

    return (
        f"http://127.0.0.1:"
        f"{NODE_PORTS[node]}/{encoded_key}"
    )


# ============================================================
# 5. RETRIEVE KEYS FROM A SERVER
# ============================================================

def read_keys(session, node):
    """
    Retrieve the list of keys stored on one server.
    """

    # Communicate directly with the storage server.
    url = (
        f"http://127.0.0.1:"
        f"{NODE_PORTS[node]}/_admin/keys"
    )

    response = session.get(
        url,
        timeout=TIMEOUT
    )

    # Stop migration if the server returns an HTTP error.
    response.raise_for_status()

    # Extract the list of stored keys.
    keys = response.json().get("keys")

    # Validate the response format.
    if not isinstance(keys, list) or any(
        not isinstance(key, str) for key in keys
    ):
        raise RuntimeError(
            f"Invalid key listing from {node}"
        )

    return keys


# ============================================================
# 6. RETRIEVE A STORED VALUE
# ============================================================

def read_value(session, node, key):
    """
    Retrieve a value directly from its storage server.
    """

    response = session.get(
        key_url(node, key),
        timeout=TIMEOUT
    )

    # Reject missing records and unexpected HTTP errors.
    response.raise_for_status()

    payload = response.json()

    # Ensure the response contains the requested value.
    if (
        not isinstance(payload, dict)
        or "value" not in payload
    ):
        raise RuntimeError(
            f"Invalid value response for {key!r} from {node}"
        )

    return payload["value"]


# ============================================================
# 7. DISCOVER KEY LOCATIONS
# ============================================================

def scan_locations(session, nodes):
    """
    Discover which physical servers currently hold each key.
    """

    locations = defaultdict(list)

    # Inspect every server involved in the migration.
    for node in nodes:

        # Retrieve that server's stored keys.
        for key in read_keys(session, node):

            # Track each server containing the key.
            locations[key].append(node)

    return dict(locations)


# ============================================================
# 8. CHECK ROUTER AVAILABILITY
# ============================================================

def ensure_router_stopped():
    """
    Prevent an active router from accepting traffic
    during a data migration.
    """

    try:
        # Check whether the router's host port is active.
        with socket.create_connection(
            ("127.0.0.1", 8080),
            timeout=1
        ):
            pass

    except OSError:
        # No service is listening on port 8080.
        return

    # Refuse to migrate while the router is available.
    raise RuntimeError(
        "Port 8080 is active. "
        "Stop kv-router-main before using --apply"
    )


# ============================================================
# 9. PLAN AND EXECUTE KEY MIGRATION
# ============================================================

def rebalance(session, old_nodes, new_nodes, apply):
    """
    Compare the old and new hash rings.

    Without --apply, display the migration plan.
    With --apply, safely redistribute the records.
    """

    # Require the router to be offline before modification.
    if apply:
        ensure_router_stopped()

    # Construct the previous consistent hash ring.
    old_ring = ConsistentHashRing(
        old_nodes,
        virtual_nodes=128
    )

    # Construct the new consistent hash ring.
    new_ring = ConsistentHashRing(
        new_nodes,
        virtual_nodes=128
    )

    # Include both previous and new servers in the scan.
    # This also detects copies from interrupted migrations.
    involved = tuple(
        dict.fromkeys(old_nodes + new_nodes)
    )

    # Discover all currently stored records.
    locations = scan_locations(
        session,
        involved
    )

    # Store the verified migration plan.
    plan = {}

    # --------------------------------------------------------
    # Phase 1: Validate records and calculate new owners.
    # --------------------------------------------------------

    for key, holders in sorted(locations.items()):

        # Retrieve every existing copy of this key.
        values = [
            read_value(session, node, key)
            for node in holders
        ]

        # Reject conflicting values across servers.
        if any(
            value != values[0]
            for value in values[1:]
        ):
            raise RuntimeError(
                f"Conflicting copies of {key!r}: {holders}"
            )

        # Determine the previous and new hash owners.
        old_owner = old_ring.get_node(key)
        new_owner = new_ring.get_node(key)

        # Reject records that are not located on either
        # their previous owner or their intended new owner.
        if (
            old_owner not in holders
            and new_owner not in holders
        ):
            raise RuntimeError(
                f"Misplaced key {key!r}; "
                "investigate before migrating"
            )

        # Preserve the destination, value, and old locations.
        plan[key] = (
            new_owner,
            values[0],
            tuple(holders)
        )

    # --------------------------------------------------------
    # Phase 2: Display the planned operations.
    # --------------------------------------------------------

    # Count records requiring a new destination copy.
    copies = sum(
        owner not in holders
        for owner, _, holders in plan.values()
    )

    # Count copies that will become obsolete.
    deletions = sum(
        sum(
            node != owner
            for node in holders
        )
        for owner, _, holders in plan.values()
    )

    print(f"Keys found: {len(plan)}")
    print(f"Copies needed: {copies}")
    print(f"Obsolete copies to delete: {deletions}")

    # Show the planned movement of each affected key.
    for key, (owner, _, holders) in plan.items():

        if owner not in holders or any(
            node != owner for node in holders
        ):
            print(
                f"  {key}: "
                f"{', '.join(holders)} -> {owner}"
            )

    # Stop here unless the user explicitly requests changes.
    if not apply:
        print(
            "DRY RUN ONLY: No records were changed."
        )
        return

    # --------------------------------------------------------
    # Phase 3: Copy records to their new owners.
    # --------------------------------------------------------

    for key, (owner, value, holders) in plan.items():

        # Skip copying if the new owner already has the key.
        if owner in holders:
            continue

        # Transfer the original value to its new server.
        response = session.post(
            key_url(owner, key),
            json={"value": value},
            timeout=TIMEOUT
        )

        # Stop if the destination rejected the write.
        response.raise_for_status()

        # Immediately verify the copied value.
        if read_value(session, owner, key) != value:
            raise RuntimeError(
                f"Copy verification failed for {key!r}"
            )

    # --------------------------------------------------------
    # Phase 4: Verify all destination records.
    # --------------------------------------------------------

    # Confirm every key is correct before deleting
    # any records from their old locations.
    for key, (owner, value, _) in plan.items():

        if read_value(session, owner, key) != value:
            raise RuntimeError(
                f"Destination verification failed "
                f"for {key!r}"
            )

    # --------------------------------------------------------
    # Phase 5: Remove obsolete copies.
    # --------------------------------------------------------

    for key, (owner, value, holders) in plan.items():

        for node in holders:

            # Never delete the correct destination copy.
            if node == owner:
                continue

            # Recheck the destination before deletion.
            if read_value(session, owner, key) != value:
                raise RuntimeError(
                    f"Destination changed before "
                    f"deleting {key!r}"
                )

            # Delete only the obsolete record.
            response = session.delete(
                key_url(node, key),
                timeout=TIMEOUT
            )

            response.raise_for_status()

    # --------------------------------------------------------
    # Phase 6: Verify final distribution.
    # --------------------------------------------------------

    # Scan all involved servers again.
    final_locations = scan_locations(
        session,
        involved
    )

    # Ensure no keys disappeared or appeared unexpectedly.
    if set(final_locations) != set(plan):
        raise RuntimeError(
            "Key count changed during migration"
        )

    # Verify that each key exists on exactly one server
    # and contains its original value.
    for key, (owner, value, _) in plan.items():

        if (
            final_locations[key] != [owner]
            or read_value(session, owner, key) != value
        ):
            raise RuntimeError(
                f"Final verification failed for {key!r}"
            )

    print(
        f"MIGRATION PASSED: {len(plan)} keys, "
        "no missing or misplaced records."
    )


# ============================================================
# 10. COMMAND-LINE ARGUMENTS
# ============================================================

def main():
    """
    Read the requested cluster membership
    and execute the migration procedure.
    """

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    # Specify the existing cluster membership.
    parser.add_argument(
        "--from-nodes",
        required=True,
        help="Old node list, e.g. kv1,kv2,kv3"
    )

    # Specify the desired cluster membership.
    parser.add_argument(
        "--to-nodes",
        required=True,
        help="New node list, e.g. kv1,kv2"
    )

    # Require explicit approval for modifications.
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform migration; default is dry run"
    )

    args = parser.parse_args()

    # Validate the supplied server lists.
    old_nodes = parse_nodes(
        args.from_nodes
    )

    new_nodes = parse_nodes(
        args.to_nodes
    )

    # Reuse HTTP connections throughout migration.
    with requests.Session() as session:

        rebalance(
            session,
            old_nodes,
            new_nodes,
            args.apply
        )


# ============================================================
# 11. PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except (
        requests.RequestException,
        RuntimeError,
        ValueError
    ) as error:

        # Stop safely when a server or validation fails.
        raise SystemExit(
            f"Migration stopped: {error}"
        ) from error
