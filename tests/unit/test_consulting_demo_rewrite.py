"""OEI-013 — invariants of the SPA's consulting question rewrite.

The demo's second act turns a customer's sentence into knowledge-base hits using
a HAND-CURATED lexicon of business terms in `demos/spa/app.js`. Two ways that
can silently rot, neither of which any other test would catch:

  1. a term is added that matches NOTHING in the catalogue — dead weight that
     looks like coverage. The lexicon is the only reason the demo's rewrite path
     returns anything at all (OEI-013 measured 0% → 44.4% hit@3 on the strength
     of it), so a term that can never match is a lie in a list of 49.
  2. a chip's question is reworded so that NO lexicon term appears in it — the
     chip then silently loses its rewrite and reverts to a query that returns
     zero hits. The chip still renders; the demo just quietly gets worse.

Everything here is checkable in Python, with no node and no JS execution.
The BEHAVIOUR of the shipped function (which terms it actually picks, and that
it is deterministic) is pinned separately, by running the real code: see
`onyx-lab/OEI-013/workspace/rewrite_probe.js` and the output in
`onyx-lab/OEI-013/evidence/04-ui-dom-proof.md`. Reimplementing the JS selection
rule in Python here would test a copy, not the code that ships.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "demos" / "spa" / "app.js"
INDEX_HTML = REPO_ROOT / "demos" / "spa" / "index.html"


@pytest.fixture(scope="module")
def js_text() -> str:
    if not APP_JS.exists():
        pytest.fail(f"SPA app.js missing at {APP_JS}")
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text() -> str:
    if not INDEX_HTML.exists():
        pytest.fail(f"SPA index.html missing at {INDEX_HTML}")
    return INDEX_HTML.read_text(encoding="utf-8")


def _js_string_array(js: str, name: str) -> list[str]:
    """Read a `var NAME = [ "a", "b", ];` literal out of the JS source."""
    m = re.search(
        rf"var\s+{re.escape(name)}\s*=\s*\[(.*?)\]\s*;", js, re.DOTALL
    )
    assert m, f"`{name}` not found in app.js — did the demo get renamed?"
    return re.findall(r'"([^"]*)"', m.group(1))


def _js_scalar(js: str, name: str) -> str:
    m = re.search(rf'var\s+{re.escape(name)}\s*=\s*"([^"]*)"\s*;', js)
    assert m, f"`{name}` not found in app.js"
    return m.group(1)


@pytest.fixture(scope="module")
def lexicon(js_text: str) -> list[str]:
    terms = _js_string_array(js_text, "CONSULTING_QUESTION_LEXICON")
    assert terms, "the lexicon is empty — the demo's rewrite path is dead"
    return terms


@pytest.fixture(scope="module")
def catalog():
    from ece.consulting.service import default_catalog

    return default_catalog()


@pytest.fixture(scope="module")
def chip_questions(html_text: str) -> list[str]:
    found = re.findall(r'class="chip"\s+data-question="([^"]+)"', html_text)
    assert found, "no question chips found in index.html"
    return found


# ---- invariant 1: every lexicon term is load-bearing ------------------------

def test_every_lexicon_term_matches_at_least_one_catalogue_object(
    lexicon: list[str], catalog
) -> None:
    """A term that matches nothing is dead weight, not coverage.

    Reported as ONE assertion listing every offender, so a regression names all
    the broken terms at once instead of failing on the first."""
    dead = [t for t in lexicon
            if not catalog.search(q=t, limit=1).items]
    assert not dead, (
        "these lexicon terms match no catalogue object and can never help: "
        f"{dead}. Either add a seed object that covers them or drop them."
    )


def test_lexicon_has_no_duplicate_terms(lexicon: list[str]) -> None:
    dupes = sorted({t for t in lexicon if lexicon.count(t) > 1})
    assert not dupes, f"duplicate lexicon terms: {dupes}"


def test_lexicon_terms_are_nonempty_and_trimmed(lexicon: list[str]) -> None:
    bad = [t for t in lexicon if not t or t != t.strip()]
    assert not bad, f"blank or untrimmed lexicon terms: {bad}"


def test_lexicon_is_ordered_longest_concept_first_enough_to_be_specific(
    lexicon: list[str],
) -> None:
    """The rewrite sorts by length, so the lexicon must CONTAIN the multi-char
    forms — otherwise the collapse has nothing specific to prefer and the cap
    fills with single characters like 采购/成本/诊断."""
    assert any(len(t) >= 4 for t in lexicon), (
        "no multi-character business term in the lexicon; the length sort "
        "would have nothing to prefer over single 2-char words"
    )


# ---- invariant 2: every demo entry point still triggers a rewrite -----------

def test_default_question_contains_a_lexicon_term(
    js_text: str, lexicon: list[str]
) -> None:
    question = _js_scalar(js_text, "CONSULTING_DEMO_QUESTION")
    hits = [t for t in lexicon if t in question]
    assert hits, (
        f"the pre-filled demo question {question!r} contains no lexicon term, "
        "so act two would open on a query that returns nothing"
    )
    assert question not in hits, (
        "the demo question IS a bare lexicon term — the act-two rewrite would "
        "be skipped as unnecessary and the act would have nothing to show"
    )


def test_every_chip_question_contains_a_lexicon_term(
    chip_questions: list[str], lexicon: list[str]
) -> None:
    broken = [q for q in chip_questions if not any(t in q for t in lexicon)]
    assert not broken, (
        "these chip questions contain no lexicon term and would silently lose "
        f"their rewrite: {broken}"
    )


def test_chip_questions_are_distinct(chip_questions: list[str]) -> None:
    assert len(set(chip_questions)) == len(chip_questions), (
        "two chips ask the same question — the presenter would appear to click "
        "a new chip and get an identical result"
    )


# ---- the audience-visible disclosure ----------------------------------------

def test_max_terms_is_a_small_positive_int(js_text: str) -> None:
    """Each term costs one library call, and each library call with a non-empty
    query also fires one engine recall — so this bounds engine load."""
    m = re.search(r"var\s+CONSULTING_REWRITE_MAX_TERMS\s*=\s*(\d+)\s*;", js_text)
    assert m, "CONSULTING_REWRITE_MAX_TERMS not found"
    assert 1 <= int(m.group(1)) <= 5, (
        f"max terms {m.group(1)} is outside the sane 1..5 band — a large value "
        "multiplies engine calls per keystroke"
    )


def test_rewrite_note_is_wired_to_an_element_the_view_defines(
    js_text: str, html_text: str
) -> None:
    """The rewrite must be DISCLOSED, not silent: the act-two note is the only
    thing telling the audience the library was searched by extracted terms."""
    assert 'var CONSULTING_REWRITE_NOTE_ID = "consulting-rewrite-note"' in js_text, (
        "the note element id is no longer a named constant; the disclosure is "
        "about to be hard-coded in two places"
    )
    assert 'id="consulting-rewrite-note"' in html_text, (
        "view D no longer defines #consulting-rewrite-note — the rewrite would "
        "happen silently"
    )
    assert "这句话不是一个关键词" in js_text, (
        "the note's customer-facing wording changed; the demo script quotes it"
    )


def test_rewrite_note_copy_names_every_term_it_searched(
    js_text: str,
) -> None:
    """The note must join the terms it actually used, not a re-derived list."""
    m = re.search(r"function\s+setConsultingRewriteNote\s*\((.*?)\)\s*\{", js_text)
    assert m, "setConsultingRewriteNote not found"
    assert "terms" in m.group(1), (
        "the note no longer takes the terms it searched, so it cannot name them"
    )
    assert 'terms.join(' in js_text, (
        "the note no longer joins the searched terms into its copy"
    )
