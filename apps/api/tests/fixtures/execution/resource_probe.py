"""Bounded resource probes used only inside the Step 6 Docker test."""

import argparse
import multiprocessing
import os
import time
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("mode")
args = parser.parse_args()

if args.mode == "timeout":
    time.sleep(30)
elif args.mode == "memory":
    block = bytearray(256 * 1024 * 1024)
    for index in range(0, len(block), 4096):
        block[index] = 1
    time.sleep(2)
elif args.mode == "pids":
    children = []
    try:
        for _ in range(128):
            child = multiprocessing.Process(target=time.sleep, args=(10,))
            child.start()
            children.append(child)
    except OSError:
        pass
    finally:
        for child in children:
            child.terminate()
        for child in children:
            child.join(timeout=1)
    if len(children) < 128:
        raise RuntimeError(f"pids limit observed after {len(children)} children")
elif args.mode == "storage":
    with Path("/tmp/storage-pressure.bin").open("wb") as handle:
        for _ in range(32):
            handle.write(b"x" * 1024 * 1024)
            handle.flush()
elif args.mode == "output":
    with Path("/outputs/output-pressure.bin").open("wb") as handle:
        for _ in range(32):
            handle.write(b"x" * 1024 * 1024)
            handle.flush()
elif args.mode == "cpu":
    end = time.monotonic() + 5
    value = 0
    while time.monotonic() < end:
        value = (value + 1) % 1000003
    Path("/outputs/cpu.json").write_text(str(value), encoding="utf-8")
else:
    raise ValueError(args.mode)
