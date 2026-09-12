"""Write a bounded effective-state receipt after M336K5 bootstrap dispatch."""

from __future__ import annotations

import argparse
import os
import site
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k5_startup import startup_receipt_from_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    startup = startup_receipt_from_path(args.startup_receipt)
    user_site = site.getusersitepackages()
    user_sites = user_site if isinstance(user_site, (list, tuple)) else (user_site,)
    membership = any(str(item) in sys.path for item in user_sites)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_STARTUP_PROBE",
        "startup_receipt_hash": startup.receipt_hash,
        "python_no_user_site_environment": os.environ.get("PYTHONNOUSERSITE"),
        "python_no_user_site_flag": sys.flags.no_user_site,
        "site_enable_user_site": bool(site.ENABLE_USER_SITE),
        "user_site_path_membership": membership,
        "python_path_present": "PYTHONPATH" in os.environ,
        "python_home_present": "PYTHONHOME" in os.environ,
        "python_user_base_present": "PYTHONUSERBASE" in os.environ,
        "python_startup_present": "PYTHONSTARTUP" in os.environ,
        "torch_imported": "torch" in sys.modules,
        "status": "PASS",
    }
    value = {**body, "receipt_hash": content_hash(body)}
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K5 startup probe output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(value))


if __name__ == "__main__":
    main()
