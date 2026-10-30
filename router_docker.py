# ============================================================
# 1. IMPORT REQUIRED LIBRARIES
# ============================================================

import asyncio
import os

from aiohttp import (
    ClientError,
    ClientSession,
    ClientTimeout,
    TCPConnector,
    web,
)

from consistent_hash import ConsistentHashRing


# ============================================================
# Router configuration
# ============================================================

# Listen on the configured HTTP port inside the container.
PORT = int(os.getenv("PORT", "8080"))

# Read backend names from the environment, removing empty entries
# and duplicates without changing the configured order.
NODE_NAMES = tuple(
    dict.fromkeys(
        name.strip()
        for name in os.getenv("KV_NODES", "kv1,kv2,kv3").split(",")
        if name.strip()
    )
)

# Each backend serves HTTP on the same internal Docker port.
BACKEND_PORT = int(os.getenv("KV_BACKEND_PORT", "8080"))

# Keep the ring configuration identical to the storage/migration tools.
VIRTUAL_NODES = 128
REQUEST_TIMEOUT = 10


# ============================================================
# Consistent hashing
# ============================================================

def create_hash_ring():
    """Build the deterministic hash ring for the configured servers."""
    if not NODE_NAMES:
        raise ValueError("At least one backend server is required")

    return ConsistentHashRing(
        nodes=NODE_NAMES,
        virtual_nodes=VIRTUAL_NODES,
    )


# ============================================================
# HTTP request forwarding
# ============================================================

async def forward_request(request):
    """Forward a GET, POST, PUT, or DELETE to the key's owner."""
    ring = request.app["hash_ring"]
    session = request.app["http_session"]

    # Choose the same physical node for a key on every request.
    key = request.match_info["key"]
    owner = ring.get_node(key)

    # Reuse a precomputed backend address and retain the incoming
    # request path and query string.
    backend_url = (
        request.app["backend_urls"][owner]
        + str(request.rel_url)
    )

    method = request.method
    body = None
    headers = None

    # Forward write bodies as bytes to avoid unnecessary JSON parsing
    # and serialization in the router.
    if method in ("POST", "PUT"):
        body = await request.read()
        content_type = request.headers.get("Content-Type")
        if content_type is not None:
            headers = {"Content-Type": content_type}

    try:
        # The shared session reuses connections to the backend servers.
        async with session.request(
            method=method,
            url=backend_url,
            data=body,
            headers=headers,
        ) as response:
            response_body = await response.read()
            response_type = response.headers.get(
                "Content-Type", "application/octet-stream"
            )

            # Preserve the backend's status, response body, and type.
            return web.Response(
                status=response.status,
                body=response_body,
                headers={"Content-Type": response_type},
            )

    except asyncio.TimeoutError:
        return web.json_response(
            {"error": "Backend request timed out"},
            status=504,
        )

    except ClientError:
        return web.json_response(
            {"error": "Backend server unavailable"},
            status=502,
        )


# ============================================================
# HTTP client lifecycle
# ============================================================

async def on_startup(app):
    """Create the reusable asynchronous backend HTTP client."""
    timeout = ClientTimeout(total=REQUEST_TIMEOUT)
    connector = TCPConnector(limit=256, ttl_dns_cache=300)

    app["http_session"] = ClientSession(
        connector=connector,
        timeout=timeout,
    )


async def on_cleanup(app):
    """Close pooled backend HTTP connections during shutdown."""
    session = app.get("http_session")
    if session is not None:
        await session.close()


# ============================================================
# Application setup
# ============================================================

def create_app():
    """Create the router with deterministic routing and shared resources."""
    app = web.Application()

    # Construct the hash ring and backend addresses once at startup.
    app["hash_ring"] = create_hash_ring()
    app["backend_urls"] = {
        node: f"http://{node}:{BACKEND_PORT}"
        for node in NODE_NAMES
    }

    # All supported methods resolve keys through the same hash ring.
    for method in ("GET", "POST", "PUT", "DELETE"):
        app.router.add_route(method, "/{key}", forward_request)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)