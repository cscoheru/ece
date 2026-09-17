"""E1 Entity Resolution runner (cut-006 §7.3 R3).

Per CUT-001 R3 acceptance:
- data/eval/e1_resolution.json with >= 50 cases incl. alias + same-name
- runner executes POST /resolve for each case
- accuracy reported as real number; if v0 < 95% report actual with gap analysis
- CI block: failure
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
        default=Path("data/eval/e1_resolution.json"),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
    )
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    cases = data["cases"]
    total = len(cases)
    print(f"Loaded {total} cases from {args.data}")

    correct = 0
    wrong = 0
    failures: list[dict] = []

    for case in cases:
        body = {
            "mention": case["mention"],
            "type_hint": case.get("type_hint"),
        }
        # cut-040R RC-3 fix: X-User-Id header must be ASCII. The `requests`
        # library encodes headers as latin-1; a Chinese mention like
        # "无限极" fails at request stage with `latin-1 codec can't encode
        # characters` BEFORE the body (which now uses utf-8 correctly) ever
        # gets serialized. Use a fixed ASCII user_ref for auth identity —
        # the actual `mention` for resolver lookup goes in the JSON body
        # (which is utf-8 encoded via the data= + Content-Type fix below).
        headers = {"X-User-Id": "demo-user-default"}
        try:
            # cut-040 R40.2: explicit UTF-8 encoding + Content-Type header.
            # `requests.post(json=body)` defaults to ensure_ascii=True which
            # escapes Chinese mentions to `无限极`; the /resolve
            # tokenizer then breaks on these escape sequences. Pre-serialize
            # to UTF-8 bytes + explicit charset header so server parses raw
            # CJK bytes (e.g. "无限极" stays as 3 UTF-8 bytes, not 18 ASCII
            # bytes of `\uXXXX`).
            r = requests.post(
                f"{args.base_url}/api/v1/resolve",
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={**headers, "Content-Type": "application/json; charset=utf-8"},
                timeout=5,
                proxies={"http": None, "https": None},  # bypass HTTP_PROXY (Clash) for localhost
            )
            response_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print(f"\n*** SKIP: cannot connect to {args.base_url}; bring up api first (make pull-db && docker compose up -d db && make seed) ***")
            return 3
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        resolved = response_body.get("resolved", False)
        expected = case.get("expected_resolved", True)

        if resolved != expected:
            wrong += 1
            failures.append({
                "case": case["id"],
                "mention": case["mention"],
                "expected": expected,
                "got": resolved,
                "reason": "resolved mismatch",
            })
            continue

        # resolved=True case: check chosen entity matches
        if expected and case.get("expected_chosen_startswith"):
            chosen = response_body.get("chosen")
            if not chosen or not chosen.startswith(case["expected_chosen_startswith"]):
                wrong += 1
                failures.append({
                    "case": case["id"],
                    "mention": case["mention"],
                    "expected_startswith": case["expected_chosen_startswith"],
                    "got": chosen,
                    "reason": "chosen mismatch",
                })
                continue

        correct += 1

    accuracy = correct / total * 100 if total else 0.0
    print("\n=== E1 Entity Resolution Results ===")
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Wrong:    {wrong}")
    print(f"Accuracy: {accuracy:.1f}%")

    if failures:
        print("\n--- First 10 Failures ---")
        for f in failures[:10]:
            print(f"  [{f.get('case')}] {f}")

    # Acceptance: per R3 — if < 95% report actual with gap analysis (allow under-target)
    if accuracy >= 95.0:
        print("\n*** PASS: >= 95% R3 acceptance ***")
        return 0
    print(f"\n*** UNDER 95% target: {accuracy:.1f}% (R3 acceptance: report under-target w/ gap analysis; do NOT claim pass) ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
