"""Build the canonical M-33.6k.8 V4 request from a strict JSON configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k8_request import (
    build_m336k8_final_route_request,
    write_m336k8_final_route_request,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(
            args.configuration.resolve(strict=True).read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise M336K2ProtocolError("M336K8 builder configuration is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K8 builder configuration is not an object")
    request = build_m336k8_final_route_request(**value)
    write_m336k8_final_route_request(request, args.output.resolve(strict=False))


if __name__ == "__main__":
    main()
