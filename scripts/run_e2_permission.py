"""E2 permission runner (cut-006 R2): execute /permissions/check for all eval cases,
count Unauthorized Exposure, fail CI if any exposure.

Per cut-006 R2 acceptance: Unauthorized Exposure = 0 is CI-blocker.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/eval/e2_permission.json"),
        help="Path to e2_permission.json",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="Base URL of ECE API (matches docker-compose port mapping R3)",
    )
    parser.add_argument(
        "--insert-deny-acls",
        action="store_true",
        help="Insert test ACL entries (DENY for ACL-DENY-TEST, ALLOW for ACL-ALLOW-CROSS-DEPT, expired ALLOW) into DB before running",
    )
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    cases = data["cases"]
    print(f"Loaded {len(cases)} cases from {args.data}")

    # Note: full integration would seed test users + ACL entries first.
    # For v0 runner, we assume the S2.1 seed_test_users + S2.4 ACL fixtures are in place.
    # The runner checks vs expected_allowed per the engine logic.

    headers_pool = {
        "demo-user-procurement": {"X-User-Id": "demo-user-procurement"},
        "demo-user-finance": {"X-User-Id": "demo-user-finance"},
        "demo-user-engineering": {"X-User-Id": "demo-user-engineering"},
        "U_other_dept": {"X-User-Id": "U_other_dept"},
    }

    unauthorized_exposures: list[dict] = []
    failures: list[dict] = []

    for case in cases:
        user_ref = case["user_ref"]
        headers = headers_pool.get(user_ref, {"X-User-Id": user_ref})
        body = {
            "user_ref": user_ref,
            "object_type": case["object_type"],
            "object_ref": case["object_ref"],
            "classification": case["classification"],
        }
        try:
            r = requests.post(
                f"{args.base_url}/api/v1/permissions/check",
                json=body,
                headers=headers,
                timeout=5,
                proxies={"http": None, "https": None},  # bypass HTTP_PROXY (Clash) for localhost
            )
            response_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print(f"\n*** SKIP: cannot connect to {args.base_url}; bring up api first (make pull-db && docker compose up -d db && make seed) ***")
            return 3  # env-not-ready exit code (distinct from logic fail)
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        allowed = response_body.get("allowed", False)

        # Identification of Unauthorized Exposure
        # Per cut-006 R2: an UNEXPECTED allow (deny expected, server returned allowed=True)
        # is an unauthorized exposure.
        if allowed and not case["expected_allowed"]:
            unauthorized_exposures.append({
                "case": case["id"],
                "user_ref": user_ref,
                "object_type": case["object_type"],
                "object_ref": case["object_ref"],
                "classification": case["classification"],
                "category": case["category"],
                "reason": "server returned allowed=True but expected allowed=False",
                "detail": case["reason"],
            })
        if not allowed and case["expected_allowed"]:
            failures.append({
                "case": case["id"],
                "user_ref": user_ref,
                "object_type": case["object_type"],
                "object_ref": case["object_ref"],
                "expected": "allow",
                "got": "deny",
                "reason": case["reason"],
            })

    total = len(cases)
    failures_count = len(failures)
    exposure_count = len(unauthorized_exposures)
    failures_pct = (failures_count + exposure_count) / total * 100 if total else 0.0

    print("\n=== E2 Permission Suite Results ===")
    print(f"Total cases:        {total}")
    print(f"Failures:           {failures_count}")
    print(f"Exposures:          {exposure_count}")
    print(f"Failure+Exposure %: {failures_pct:.1f}%")

    if failures:
        print("\n--- Failures (Expected allow but got deny) ---")
        for f in failures[:10]:
            print(f"  [{f['case']}] user={f['user_ref']} {f['object_type']}/{f['object_ref']} cls={f.get('expected')} -- {f['reason']}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")

    if unauthorized_exposures:
        print("\n--- UNAUTHORIZED EXPOSURES (FAIL-CLOSED must be 0; CI blocker) ---")
        for e in unauthorized_exposures[:10]:
            print(f"  [{e['case']}] user={e['user_ref']} {e['object_type']}/{e['object_ref']} cls={e['classification']} cat={e['category']} -- {e['reason']}")
        if len(unauthorized_exposures) > 10:
            print(f"  ... and {len(unauthorized_exposures) - 10} more")

    # Acceptance: per cut-006 R2 — Unauthorized Exposure = 0 (one-line verdict)
    if exposure_count > 0:
        print(f"\n*** FAIL: {exposure_count} Unauthorized Exposure(s); CI blocked (cut-006 R2) ***")
        return 2  # CI exit code
    if failures_count > 0:
        print(f"\n*** FAIL: {failures_count} permission check failure(s) ***")
        return 1
    print("\n*** PASS: 0 Unauthorized Exposure, 0 permission failure (cut-006 R2) ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
