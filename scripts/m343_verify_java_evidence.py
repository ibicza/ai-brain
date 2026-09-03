"""Fresh-process verifier for an M-34.3 compiled Java evidence closure."""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

from ai_brain.stage3.acquisition.java_replay import (
    verify_compiled_java_evidence_standalone,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    attempts = 0
    if os.environ.get("M343_NO_NETWORK") != "1":
        raise RuntimeError("M-34.3 standalone replay requires M343_NO_NETWORK=1")

    def blocked_socket(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise PermissionError("network forbidden during M-34.3 replay")

    socket.socket = blocked_socket
    socket.create_connection = blocked_socket
    report = {
        **verify_compiled_java_evidence_standalone(args.pack),
        "socket_attempts": attempts,
    }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
