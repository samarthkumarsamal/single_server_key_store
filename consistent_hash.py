# ============================================================
# 1. IMPORT REQUIRED LIBRARIES
# ============================================================

# Binary search provides efficient lookups in a sorted ring.
from bisect import bisect_left

# SHA-256 provides stable, deterministic hash values.
from hashlib import sha256

# Type hints improve readability and maintainability.
from typing import Iterable


# ============================================================
# 2. CONSISTENT HASH RING
# ============================================================

class ConsistentHashRing:
    """
    Distribute keys across multiple servers using
    SHA-256 and a configurable number of virtual nodes.
    """

    def __init__(
        self,
        nodes: Iterable[str] = (),
        virtual_nodes: int = 128
    ):
        # Require at least one virtual node per server.
        if virtual_nodes < 1:
            raise ValueError(
                "virtual_nodes must be greater than zero"
            )

        # Number of virtual positions assigned to each server.
        self.virtual_nodes = virtual_nodes

        # Sorted SHA-256 positions on the hash ring.
        self._positions = []

        # Server name corresponding to each ring position.
        self._owners = []

        # Set of physical servers currently in the ring.
        self._nodes = set()

        # Register the initial physical servers.
        for node in nodes:
            self.add_node(node)

    # ========================================================
    # 3. SHA-256 HASH FUNCTION
    # ========================================================

    @staticmethod
    def _hash(value: str) -> int:
        """
        Convert a string into a deterministic
        256-bit integer using SHA-256.
        """

        # Encode the string into UTF-8 bytes.
        encoded_value = value.encode("utf-8")

        # Generate the SHA-256 digest.
        digest = sha256(encoded_value).digest()

        # Convert the digest into an integer for comparison.
        return int.from_bytes(
            digest,
            byteorder="big"
        )

    # ========================================================
    # 4. ADD A PHYSICAL SERVER
    # ========================================================

    def add_node(self, node: str) -> None:
        """
        Add a server and its virtual nodes to the ring.
        """

        # Require a valid server name.
        if not isinstance(node, str) or not node:
            raise ValueError(
                "Server name must be a non-empty string"
            )

        # Avoid registering the same server twice.
        if node in self._nodes:
            return

        # Generate the configured number of virtual nodes.
        for replica in range(self.virtual_nodes):

            # Create a unique identifier for each replica.
            virtual_name = f"{node}:{replica}"

            # Calculate the replica's position in the ring.
            position = self._hash(virtual_name)

            # Find the correct sorted insertion position.
            index = bisect_left(
                self._positions,
                position
            )

            # Insert the position and its physical server.
            self._positions.insert(
                index,
                position
            )

            self._owners.insert(
                index,
                node
            )

        # Record the physical server as active.
        self._nodes.add(node)

    # ========================================================
    # 5. REMOVE A PHYSICAL SERVER
    # ========================================================

    def remove_node(self, node: str) -> None:
        """
        Remove a physical server and all its
        associated virtual positions.
        """

        # Ignore servers that are not currently registered.
        if node not in self._nodes:
            return

        # Retain only positions belonging to other servers.
        remaining = [
            (position, owner)
            for position, owner in zip(
                self._positions,
                self._owners
            )
            if owner != node
        ]

        # Rebuild the sorted position and owner lists.
        self._positions = [
            position for position, _ in remaining
        ]

        self._owners = [
            owner for _, owner in remaining
        ]

        # Remove the physical server from the active set.
        self._nodes.remove(node)

    # ========================================================
    # 6. FIND THE OWNER OF A KEY
    # ========================================================

    def get_node(self, key: str) -> str:
        """
        Find the physical server responsible for a key.

        A key belongs to the first virtual node found
        clockwise from its SHA-256 position.
        """

        # A key cannot be assigned without any servers.
        if not self._positions:
            raise RuntimeError(
                "No servers available in the hash ring"
            )

        # Calculate the key's hash-ring position.
        key_position = self._hash(key)

        # Find the first virtual node at or after the key.
        index = bisect_left(
            self._positions,
            key_position
        )

        # Wrap around to the beginning of the ring.
        if index == len(self._positions):
            index = 0

        # Return the physical server owning this position.
        return self._owners[index]

    # ========================================================
    # 7. INSPECT ACTIVE SERVERS
    # ========================================================

    @property
    def nodes(self) -> tuple[str, ...]:
        """
        Return the registered physical server names.
        """

        return tuple(sorted(self._nodes))

    @property
    def ring_size(self) -> int:
        """
        Return the total number of virtual positions.
        """

        return len(self._positions)