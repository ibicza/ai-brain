"""Fresh-process verifier for a compiled M-34.2 Java evidence closure."""

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
    socket_attempts = 0
    if os.environ.get("M342_NO_NETWORK") == "1":

        def blocked_socket(*_args, **_kwargs):
            nonlocal socket_attempts
            socket_attempts += 1
            raise RuntimeError("network disabled by M-34.2 acceptance guard")

        socket.socket = blocked_socket
        socket.create_connection = blocked_socket
    report = {
        **verify_compiled_java_evidence_standalone(args.pack),
        "socket_attempts": socket_attempts,
    }
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
