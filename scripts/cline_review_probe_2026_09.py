"""Cline adversarial probe — v0.2 handoff review (2026-09).

Probes (in-process TestClient, env set at runtime since parsers read os.environ per call):
  P1  JWT-mode impersonation: ECE_JWT_SECRET set, NO Authorization, only X-User-Id -> 200?
  P2  Invalid JWT silently downgrades to X-User-Id -> 200?
  P3  Revoked USER + valid per-resource token -> 200? (cut-028 says denied ALL access)
  P4  Rate-limit bucket rotation via unvalidated X-Org-Id header (single-tenant)
"""
import os
import uuid

os.environ["ECE_JWT_SECRET"] = "cline-review-topsecret"

from fastapi.testclient import TestClient  # noqa: E402

from ece.db import get_engine  # noqa: E402
from ece.main import app  # noqa: E402

client = TestClient(app)

# --- seed a trace row directly ---
rid = str(uuid.uuid4())
eng = get_engine()
with eng.begin() as conn:
    conn.execute(
        __import__("sqlalchemy").text(
            "INSERT INTO context_requests"
            " (request_id, user_ref, intent, root_entities, counts, status, org_id)"
            " VALUES (:r, 'alice', 'probe', '[]'::jsonb, '{}'::jsonb, 'ok', 'org_a')"
        ),
        {"r": rid},
    )

print(f"trace seeded rid={rid}")

# P1: JWT mode ON, caller omits Authorization, claims alice via X-User-Id
r = client.get(f"/api/v1/audit/context/{rid}", headers={"X-User-Id": "alice"})
print(f"P1 jwt-mode x-user-id impersonation: {r.status_code}"
      + ("  <-- AUTH BYPASS" if r.status_code == 200 else "  (blocked)"))

# P2: garbage JWT + X-User-Id
r = client.get(
    f"/api/v1/audit/context/{rid}",
    headers={"Authorization": "Bearer garbage.token.here", "X-User-Id": "alice"},
)
print(f"P2 invalid-jwt silent downgrade:    {r.status_code}"
      + ("  <-- AUTH BYPASS" if r.status_code == 200 else "  (blocked)"))

# P3: revoked user + per-resource token (per cut-028 "denied ALL access")
os.environ["ECE_REVOKED_USERS"] = "alice"
os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{rid}"
r = client.get(f"/api/v1/audit/context/{rid}", headers={"X-Delegation-Token": "audit_tok"})
print(f"P3a revoked-user, token only:        {r.status_code}")
r = client.get(
    f"/api/v1/audit/context/{rid}",
    headers={"X-User-Id": "alice", "X-Delegation-Token": "audit_tok"},
)
print(f"P3b revoked-user + x-user-id + tok:  {r.status_code}"
      + ("  <-- cut-028 invariant violated" if r.status_code == 200 else "  (blocked)"))
del os.environ["ECE_REVOKED_USERS"]
del os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"]

# P4: single-tenant rate-limit evasion via header rotation
os.environ.pop("ECE_USER_ORGS", None)
os.environ["ECE_ORG_RATE_LIMITS"] = "org_a:2/m"
from ece.api.rate_limit import reset_buckets  # noqa: E402

reset_buckets()
codes = [
    client.get(f"/api/v1/audit/context/{rid}",
               headers={"X-User-Id": "alice", "X-Org-Id": "org_a"}).status_code
    for _ in range(3)
]
rotated = client.get(f"/api/v1/audit/context/{rid}",
                     headers={"X-User-Id": "alice", "X-Org-Id": "org_b"}).status_code
print(f"P4 rate-limit org_a x3: {codes} (expect 3rd=429)")
print(f"P4 rotate header -> org_b:            {rotated}"
      + ("  <-- bucket rotation evasion" if rotated == 200 else "  (blocked)"))
