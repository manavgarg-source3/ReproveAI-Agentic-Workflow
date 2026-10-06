"""Safe runtime-boundary probe; it never writes outside /outputs."""

import json
import os
import socket
from pathlib import Path


def can_read(path: str) -> bool:
    try:
        Path(path).read_bytes()
        return True
    except (OSError, PermissionError):
        return False


paths = {
    "workspace_env": can_read("/workspace/.env"),
    "host_app_marker": can_read("/host-application-marker"),
    "home": can_read("/root/.bashrc"),
    "ssh": can_read("/root/.ssh/id_rsa"),
    "host_arbitrary": can_read("/host-secret-marker"),
}
network = {}
for name, address in {
    "localhost": ("127.0.0.1", 8000),
    "external": ("1.1.1.1", 80),
}.items():
    try:
        with socket.create_connection(address, timeout=1):
            network[name] = True
    except OSError:
        network[name] = False

secret_names = {
    name for name in os.environ
    if name != "GPG_KEY"  # Public package-signing metadata baked into the base image.
    if any(term in name.upper() for term in ("KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL", "JWT"))
}
result = {"paths": paths, "network": network, "secret_names": sorted(secret_names)}
print(json.dumps(result, sort_keys=True))
Path("/outputs/security.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
