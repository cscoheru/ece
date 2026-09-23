"""cut-045 closure-archive R4-B2 — Committed ops evidence redaction.

Codex R3 final gate: reports under ``reports/cut-045-operations/`` and the
ops report itself (``reports/cut-045-operations-report.md``) must not
contain raw origin infrastructure details that could weaken source-host
hiding — even though the repo is not yet public, source IP / IPv6 / root
SSH user / Cloudflare zone_id are not committed.

These binding tests assert:
  1. No raw IPv4 address anywhere in the committed ops evidence.
  2. No raw IPv6 address anywhere in the committed ops evidence.
  3. No "root@..." or "root SSH" user references in the committed ops evidence.
  4. No Cloudflare zone_id (32-hex) in the committed ops evidence.
  5. REDACTED_* placeholders ARE present (positive sanity — prevents
     subsequent cycles from silently dropping the placeholder rather than
     performing real redaction).

Path scope: ``reports/cut-045-operations-report.md`` + everything under
``reports/cut-045-operations/``. Other reports / closure docs are out
of scope (those follow a different redaction policy if any).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_REPORT = REPO_ROOT / "reports" / "cut-045-operations-report.md"
OPS_DIR = REPO_ROOT / "reports" / "cut-045-operations"


def _ops_files() -> list[Path]:
    """All .md / .txt files under reports/cut-045-operations/ (recursively)."""
    if not OPS_DIR.exists():
        pytest.fail(f"Ops evidence dir missing: {OPS_DIR}")
    files = sorted(p for p in OPS_DIR.rglob("*") if p.is_file() and p.suffix in (".md", ".txt"))
    if not files:
        pytest.fail(f"No .md/.txt evidence files under {OPS_DIR}")
    return files


def _all_evidence_paths() -> list[Path]:
    """Ops report + every text file under ops dir (relative to REPO_ROOT)."""
    paths: list[Path] = []
    if OPS_REPORT.exists():
        paths.append(OPS_REPORT)
    paths.extend(_ops_files())
    return paths


@pytest.fixture(scope="module")
def evidence_files() -> dict[Path, str]:
    """{absolute_path: text} for all committed ops evidence."""
    return {p: p.read_text(encoding="utf-8") for p in _all_evidence_paths()}


# ---------------------------------------------------------------------------
# Forbidden patterns (compiled regex; match anywhere in committed evidence)
# ---------------------------------------------------------------------------

# IPv4: 4 octets 0-255 separated by dots. Word-boundary on both sides.
# Allowed (public, non-source): loopback (127.0.0.0/8), unspecified (0.0.0.0),
# public resolvers (8.8.8.8/8.8.4.4, 1.1.1.1/1.0.0.1, 9.9.9.9/149.112.112.112),
# Cloudflare edge IPs (currently 104.16.0.0/12, 172.64.0.0/13, 173.245.48.0/20,
# 188.114.96.0/20, 197.234.240.0/22, 198.41.128.0/17, 162.158.0.0/15,
# 141.101.64.0/18, 131.0.72.0/22, 190.93.240.0/20, 188.114.96.0/20,
# 173.245.48.0/20 — represented as 172.67.x, 104.21.x, 104.16.x, 172.64.x,
# 162.159.x, 188.114.x, 141.101.x, 131.0.x, 190.93.x, 173.245.x). These are
# well-known public constants, not origin infrastructure.
ALLOWED_IPV4_PREFIXES = (
    "127.",       # loopback (RFC 1122)
    "0.0.0.0",    # unspecified
    "8.8.8.8", "8.8.4.4",                  # Google Public DNS
    "1.1.1.1", "1.0.0.1",                  # Cloudflare Public DNS (separate from edge)
    "9.9.9.9", "149.112.112.112",          # Quad9 DNS
    "104.16.", "104.17.", "104.18.", "104.19.", "104.20.", "104.21.", "104.22.", "104.23.", "104.24.", "104.25.", "104.26.", "104.27.", "104.28.", "104.29.", "104.30.", "104.31.",  # CF
    "172.64.", "172.65.", "172.66.", "172.67.", "172.68.", "172.69.", "172.70.", "172.71.",  # CF
    "162.158.", "162.159.",  # CF
    "188.114.",  # CF
    "141.101.",  # CF
    "131.0.72.",  # CF
    "190.93.",  # CF
    "173.245.48.", "173.245.49.", "173.245.50.", "173.245.51.", "173.245.52.", "173.245.53.", "173.245.54.", "173.245.55.",  # CF
    "198.41.",  # CF
    "197.234.240.", "197.234.241.", "197.234.242.", "197.234.243.",  # CF
)
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _is_allowed_ipv4(addr: str) -> bool:
    """Return True if addr is a well-known public constant (loopback, public
    DNS, Cloudflare edge), which is NOT origin infrastructure."""
    return any(addr.startswith(p) for p in ALLOWED_IPV4_PREFIXES)


# IPv6: at least 3 hextet groups (skip "hh:mm:ss" time and "ab:cd" prose).
# Allowed (non-origin): loopback (::1), link-local (fe80::/10), unique-local
# (fc00::/7), unspecified (::). Source IPv6 was server outbound CMCC, not in
# these ranges — so any match against committed evidence is a real leak.
IPV6_RE = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){3,}[0-9a-fA-F:]+\b"
)


def _is_allowed_ipv6(addr: str) -> bool:
    """Return True if addr is loopback/link-local/ULA/unspecified."""
    a = addr.lower()
    return (
        a.startswith("::1")
        or a.startswith("fe80:")
        or a.startswith("fc00:") or a.startswith("fd00:")
        or a == "::"
    )


# root SSH user: literal "root@host" or "root SSH user" / "root SSH" phrase.
# NOT matching "/root/.secrets" (filesystem path) or "ISRG Root YR" (cert name).
ROOT_SSH_RE = re.compile(r"\broot(?:@|\s+SSH)", re.IGNORECASE)

# CF zone_id: 32 hex chars after "zone_id=" (case-insensitive).
CF_ZONE_ID_RE = re.compile(r"zone_id\s*=\s*[0-9a-fA-F]{20,}", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Tests (one file per test, parametrize via fixture iteration)
# ---------------------------------------------------------------------------


def _per_file_check(
    name: str,
    evidence: dict[Path, str],
    pattern: re.Pattern[str],
    description: str,
    allow_filter=None,
) -> None:
    """Helper: assert no file in evidence matches pattern (after allow_filter)."""
    offenders = []
    for p, text in evidence.items():
        raw_matches = list(pattern.finditer(text))
        if allow_filter is not None:
            matches = [m for m in raw_matches if not allow_filter(m.group())]
        else:
            matches = raw_matches
        if matches:
            offenders.append((p, [m.group() for m in matches]))
    assert not offenders, (
        f"{name}: raw {description} leaked in committed ops evidence:\n"
        + "\n".join(f"  - {p.relative_to(REPO_ROOT)}: {vals}" for p, vals in offenders)
        + "\nReplace with <REDACTED_*> placeholder. See cut-045 closure-archive R4-B2."
    )


def test_no_ipv4_in_ops_evidence(evidence_files: dict[Path, str]) -> None:
    """No raw IPv4 address may appear in committed ops evidence.

    Codex R3 R4-B2: source IPv4 weakens source-host hiding. Placeholders
    ``<REDACTED_ORIGIN_IPV4>`` are required instead.

    Allowed (well-known public constants, NOT origin infrastructure):
    loopback (127.0.0.0/8), unspecified (0.0.0.0), public resolvers
    (8.8.8.8, 1.1.1.1, 9.9.9.9), Cloudflare edge IP ranges.
    """
    _per_file_check(
        "test_no_ipv4_in_ops_evidence",
        evidence_files,
        IPV4_RE,
        "IPv4 address",
        allow_filter=_is_allowed_ipv4,
    )


def test_no_ipv6_in_ops_evidence(evidence_files: dict[Path, str]) -> None:
    """No raw IPv6 address may appear in committed ops evidence.

    Codex R3 R4-B2: server's IPv6 (<REDACTED_ORIGIN_IPV6>) revealed
    before redaction. Placeholders required.

    Allowed (non-origin): loopback (::1), link-local (fe80::/10),
    unique-local (fc00::/7, fd00::/8), unspecified (::).
    """
    _per_file_check(
        "test_no_ipv6_in_ops_evidence",
        evidence_files,
        IPV6_RE,
        "IPv6 address",
        allow_filter=_is_allowed_ipv6,
    )


def test_no_root_ssh_user_in_ops_evidence(evidence_files: dict[Path, str]) -> None:
    """No literal 'root@' or 'root SSH user' may appear in committed ops evidence.

    Codex R3 R4-B2: explicit 'SSH user = root' reveals privilege level.
    Note: filesystem paths like '/root/.secrets/' and cert names like
    'ISRG Root YR' are NOT considered leaks (different semantics).
    """
    _per_file_check("test_no_root_ssh_user_in_ops_evidence", evidence_files, ROOT_SSH_RE, "'root@' or 'root SSH' phrase")


def test_no_cf_zone_id_in_ops_evidence(evidence_files: dict[Path, str]) -> None:
    """No Cloudflare zone_id (32 hex) may appear in committed ops evidence.

    Codex R3 R4-B2: zone_id uniquely identifies the Cloudflare zone,
    enabling targeted DNS attacks / takeover attempts. Placeholders
    ``<REDACTED_ZONE_ID>`` are required instead.
    """
    _per_file_check("test_no_cf_zone_id_in_ops_evidence", evidence_files, CF_ZONE_ID_RE, "Cloudflare zone_id")


def test_redacted_placeholders_intact(evidence_files: dict[Path, str]) -> None:
    """<REDACTED_*> placeholders MUST be present (positive sanity check).

    R9-derived lesson: an honest placeholder is better than silent
    omission. This test catches the failure mode where a future cycle
    "cleans up" the redaction by deleting the line entirely rather than
    substituting the placeholder.
    """
    all_text = "\n".join(evidence_files.values())
    required_placeholders = (
        "<REDACTED_ORIGIN_IPV4>",
        "<REDACTED_ORIGIN_IPV6>",
        "<REDACTED_ZONE_ID>",
    )
    missing = [p for p in required_placeholders if p not in all_text]
    assert not missing, (
        f"Expected redaction placeholders {required_placeholders} in "
        f"committed ops evidence; missing: {missing}. "
        f"R9-derived: an honest placeholder beats silent omission. "
        f"If you're removing an infrastructure reference, replace with "
        f"the <REDACTED_*> placeholder, don't just delete the line. "
        f"See cut-045 closure-archive R4-B2."
    )


def test_evidence_files_collected() -> None:
    """Sanity: evidence_files fixture must produce ≥2 files (ops report + ≥1 evidence file).

    This guards against a future reorganization that silently moves
    evidence files outside ``reports/cut-045-operations/`` and breaks
    the other 5 binding tests' coverage.
    """
    paths = _all_evidence_paths()
    assert len(paths) >= 2, (
        f"Expected ≥2 committed ops evidence files (ops report + ≥1 evidence file); "
        f"got {len(paths)}: {[p.relative_to(REPO_ROOT) for p in paths]}. "
        f"Cut-045 closure-archive R4-B2 binding tests cover files in this dir; "
        f"if you move evidence files, update the binding test scope."
    )
