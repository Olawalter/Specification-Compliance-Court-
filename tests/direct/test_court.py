"""The lifecycle: a specification, its versions, a submission, an assessment, and
the certificate each path leads to."""

import json

from tests.direct import support as s

LATER = "2026-10-05T13:30:00Z"


def cert(court, submission_id, as_of=s.NOW):
    c = court.get_certificate(submission_id, as_of)
    return (c["status"], c["verdict"], c["compliant"], c["final_by"])


# -- specifications ---------------------------------------------------------------

def test_a_specification_is_published_once_and_frozen(court, direct_vm, direct_alice, mod):
    spec_id = s.published(court, direct_vm, direct_alice)
    got = court.get_spec(spec_id, 1)
    assert spec_id == "SPEC-000001" and got["found"] and got["version"] == 1
    assert got["issuer"] == s.hexaddr(direct_alice) and got["is_latest"] is True
    assert got["spec_hash"] == mod._sha256_hex(mod._canonical(got["spec"]))
    assert [c["id"] for c in got["spec"]["clauses"]] == ["k1", "k2", "k3", "k4", "k5"]
    assert court.list_specs(0, 10)["ids"] == [spec_id]
    # there is no write that takes new text for an existing version
    assert not any(hasattr(court, name) for name in ("amend_spec", "update_spec", "set_spec"))


def test_revising_creates_a_new_version_and_leaves_the_old_one(court, direct_vm, direct_alice,
                                                              direct_bob):
    spec_id = s.published(court, direct_vm, direct_alice)
    before = court.get_spec(spec_id, 1)["spec_hash"]
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only the issuer revises"):
        court.revise_spec(spec_id, s.spec_json(title="Another title (test only)"))
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("this is the current version, unchanged"):
        court.revise_spec(spec_id, s.spec_json())
    with direct_vm.expect_revert("unknown spec_id"):
        court.revise_spec("SPEC-000404", s.spec_json())
    assert court.revise_spec(spec_id, s.spec_json(certificate_ttl=86400)) == "2"
    versions = court.get_spec_versions(spec_id)
    assert versions["latest_version"] == 2 and len(versions["versions"]) == 2
    assert court.get_spec(spec_id, 1)["spec_hash"] == before
    assert court.get_spec(spec_id, 1)["is_latest"] is False
    assert court.get_spec(spec_id, 2)["spec"]["certificate_ttl"] == 86400
    assert court.get_spec(spec_id, 3)["found"] is False


def test_a_retired_version_takes_no_new_submissions(court, direct_vm, direct_alice,
                                                    direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only the issuer retires"):
        court.retire_version("SPEC-000001", 1)
    direct_vm.sender = direct_alice
    assert court.retire_version("SPEC-000001", 1) == "RETIRED"
    with direct_vm.expect_revert("already retired"):
        court.retire_version("SPEC-000001", 1)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("retired and takes no new submissions"):
        court.submit("SPEC-000001", 1, json.dumps(s.submission("Another subject")))
    # what was submitted runs its course, and its certificate says the version retired
    direct_vm.warp(LATER)
    court.finalize(submission_id)
    c = court.get_certificate(submission_id, LATER)
    assert c["compliant"] is True and c["spec_retired"] is True


# -- submissions -------------------------------------------------------------------

def test_a_submission_pins_its_evidence(court, direct_vm, direct_alice, direct_bob):
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob)
    got = court.get_submission(submission_id)
    assert submission_id == "SUB-000001" and got["status"] == "SUBMITTED"
    assert got["submitter"] == s.hexaddr(direct_bob) and got["issuer"] == s.hexaddr(direct_alice)
    assert got["documents"] == [
        {"evidence_id": "docs", "label": "Documentation", "sha256": s.digest(s.DOCS),
         "urls": [s.DOCS_URL]},
        {"evidence_id": "metadata", "label": "Sample token metadata",
         "sha256": s.digest(s.META), "urls": [s.META_URL]}]
    assert got["values"] == {"contract": s.COLLECTION, "project": "Lumen Kites"}
    assert got["values_are_claims"] is True and got["attempt"] == 1
    assert got["window_ends"] == "2026-10-05T13:00:00Z"
    assert court.get_certificate(submission_id, s.NOW)["verdict"] == "PENDING"


def test_an_issuer_does_not_certify_under_its_own_specification(court, direct_vm,
                                                                direct_alice):
    spec_id = s.published(court, direct_vm, direct_alice)
    with direct_vm.expect_revert("does not certify a subject under its own specification"):
        court.submit(spec_id, 1, json.dumps(s.submission()))


def test_a_submission_can_be_withdrawn_before_any_round(court, direct_vm, direct_alice,
                                                        direct_bob, direct_charlie):
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("only the submitter withdraws"):
        court.withdraw_submission(submission_id)
    direct_vm.sender = direct_bob
    assert court.get_actions(submission_id, s.NOW)["may_withdraw"] is True
    assert court.withdraw_submission(submission_id) == "WITHDRAWN"
    assert cert(court, submission_id) == ("WITHDRAWN", "PENDING", False,
                                          "WITHDRAWN_BY_SUBMITTER")
    with direct_vm.expect_revert("only a SUBMITTED submission is assessed"):
        court.assess(submission_id)
    # it did not use up one of the subject's three - and its number is not reused
    again = court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    assert court.get_submission(again)["attempt"] == 2
    bob = s.hexaddr(direct_bob)
    assert court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", s.NOW)["attempts"] == 1
    # once a round is on the record there is nothing to withdraw
    s.panel(direct_vm, s.answers())
    court.assess(again)
    with direct_vm.expect_revert("only a submission no round has been asked for"):
        court.withdraw_submission(again)


def test_a_submission_past_its_window_lapses_and_is_not_withdrawn(court, direct_vm,
                                                                  direct_alice, direct_bob):
    """Withdrawing after the window closed would dodge the verdict the window's
    end stands for."""
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    direct_vm.sender = direct_bob
    actions = court.get_actions(submission_id, LATER)
    assert actions["may_withdraw"] is False and actions["may_lapse"] is True
    with direct_vm.expect_revert("the assessment window closed at"):
        court.withdraw_submission(submission_id)
    assert court.lapse(submission_id) == "UNVERIFIABLE"


# -- the assessment and the verdict rule -------------------------------------------

def test_every_mandatory_clause_met_is_compliant(court, direct_vm, direct_alice, direct_bob,
                                                 direct_charlie):
    submission_id, resolution_id = s.assessed(court, direct_vm, direct_alice, direct_bob)
    c = court.get_certificate(submission_id, s.NOW)
    assert c["status"] == "ASSESSED" and c["final"] is False and c["compliant"] is False
    assert c["verdict"] == "COMPLIANT" and c["resolution_id"] == resolution_id
    assert c["states"] == {"k1": "MET", "k2": "MET", "k3": "MET", "k4": "MET",
                           "k5": "NOT_MET"}
    # the optional clause is reported and never changes the verdict
    assert c["tally"] == {"mandatory": 4, "mandatory_met": 4, "optional": 1,
                          "optional_met": 0}
    record = s.record_of(court, resolution_id)
    assert record["applied"] is True and record["reason_code"] == "ASSESSED"
    assert [(f["id"], f["by"]) for f in record["findings"]] == [
        ("k1", "PANEL"), ("k2", "CODE"), ("k3", "CODE"), ("k4", "CODE"), ("k5", "PANEL")]
    assert s.finding_in(record, "k1")["quotes"] == [{"evidence_id": "docs",
                                                     "text": s.ROYALTY_LINE}]
    assert record["lookups"] == [{"clause": "k2", "chain": "main", "address": s.COLLECTION,
                                  "result": "CODE"}]
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("the contest window closes at"):
        court.finalize(submission_id)
    direct_vm.warp(LATER)
    assert court.finalize(submission_id) == "COMPLIANT"
    assert cert(court, submission_id, LATER) == ("FINAL", "COMPLIANT", True, "ASSESSED")


def test_some_mandatory_clauses_met_is_partial_and_none_is_non_compliant(
        court, direct_vm, direct_alice, direct_bob, direct_charlie, mod):
    partial, _r = s.assessed(court, direct_vm, direct_alice, direct_bob,
                             said_by_panel=s.answers(k1="NOT_MET"))
    assert court.get_certificate(partial, s.NOW)["verdict"] == "PARTIALLY_COMPLIANT"
    direct_vm.clear_mocks()
    empty = s.page("Coming soon", ["This page is on its way."])
    none, _r = s.assessed(
        court, direct_vm, direct_alice, direct_charlie, spec_id="SPEC-000001",
        pages={s.DOCS_URL: empty, s.META_URL: "not json"}, code="0x",
        said_by_panel=s.answers(k1="NOT_MET"))
    c = court.get_certificate(none, s.NOW)
    assert c["verdict"] == "NON_COMPLIANT" and set(c["states"].values()) == {"NOT_MET"}
    # the rule, clause by clause: the verdict follows the mandatory clauses alone
    spec = s.spec()
    for states, verdict in (
            ({"k1": "MET", "k2": "MET", "k3": "MET", "k4": "MET", "k5": "NOT_MET"}, "COMPLIANT"),
            ({"k1": "MET", "k2": "MET", "k3": "MET", "k4": "MET", "k5": "MET"}, "COMPLIANT"),
            ({"k1": "NOT_MET", "k2": "MET", "k3": "MET", "k4": "MET", "k5": "MET"},
             "PARTIALLY_COMPLIANT"),
            ({"k1": "NOT_MET", "k2": "NOT_MET", "k3": "NOT_MET", "k4": "MET",
              "k5": "NOT_MET"}, "PARTIALLY_COMPLIANT"),
            ({"k1": "NOT_MET", "k2": "NOT_MET", "k3": "NOT_MET", "k4": "NOT_MET",
              "k5": "MET"}, "NON_COMPLIANT")):
        assert mod._verdict(spec, states) == verdict, states


def test_an_optional_clause_that_is_met_is_counted(court, direct_vm, direct_alice, direct_bob):
    submission_id, _r = s.assessed(
        court, direct_vm, direct_alice, direct_bob, pages={s.DOCS_URL: s.DOCS_FULL},
        said_by_panel=s.answers(k5="MET"))
    c = court.get_certificate(submission_id, s.NOW)
    assert c["verdict"] == "COMPLIANT" and c["tally"]["optional_met"] == 1


def test_a_specification_of_checks_alone_needs_no_panel(court, direct_vm, direct_alice,
                                                       direct_bob):
    checks = [c for c in s.clauses() if c["kind"] == "CHECK"]
    submission_id, resolution_id = s.assessed(court, direct_vm, direct_alice, direct_bob,
                                              clauses=checks, said_by_panel={})
    record = s.record_of(court, resolution_id)
    assert (record["panel_state"], record["reason_code"], record["outcome"]) == \
        ("NOT_NEEDED", "CHECKS_ONLY", "COMPLIANT")
    assert s.replay(direct_vm) is True


def test_only_a_submitted_submission_is_assessed_and_only_in_its_window(
        court, direct_vm, direct_alice, direct_bob):
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    with direct_vm.expect_revert("the assessment window closed at"):
        court.assess(submission_id)
    with direct_vm.expect_revert("unknown submission_id"):
        court.assess("SUB-000404")


# -- the contest -------------------------------------------------------------------

def test_each_party_has_one_contest_and_each_restarts_the_window(
        court, direct_vm, direct_alice, direct_bob, direct_charlie):
    submission_id, first = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("only the submitter or the issuer contests"):
        court.contest(submission_id)
    direct_vm.warp("2026-10-05T12:50:00Z")
    s.panel(direct_vm, s.answers(k1="NOT_MET"))
    direct_vm.sender = direct_alice                      # the issuer
    second = court.contest(submission_id)
    assert s.record_of(court, second)["supersedes"] == first
    assert court.get_certificate(submission_id, s.NOW)["verdict"] == "PARTIALLY_COMPLIANT"
    assert court.get_submission(submission_id)["window_ends"] == "2026-10-05T13:50:00Z"
    with direct_vm.expect_revert("this party has contested this assessment once already"):
        court.contest(submission_id)
    assert court.get_actions(submission_id, "2026-10-05T12:55:00Z")["may_contest"] == \
        {"submitter": True, "issuer": False}
    s.panel(direct_vm, s.answers())
    direct_vm.sender = direct_bob
    court.contest(submission_id)
    assert court.get_certificate(submission_id, s.NOW)["verdict"] == "COMPLIANT"
    direct_vm.warp("2026-10-05T14:00:00Z")
    court.finalize(submission_id)
    assert [r["applied"] for r in court.get_history(submission_id)["rounds"]] == [True] * 3
    with direct_vm.expect_revert("only an ASSESSED submission is contested"):
        court.contest(submission_id)


def test_a_contest_after_its_window_is_refused(court, direct_vm, direct_alice, direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("the contest window closed at"):
        court.contest(submission_id)


# -- certificates and the registry ------------------------------------------------------

def test_standing_is_a_submitters_own_and_nobody_elses(court, direct_vm, direct_alice,
                                                      direct_bob, direct_charlie):
    good, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.clear_mocks()
    # a third party submits junk under the same subject's name
    junk = s.page("Coming soon", ["This page is on its way."])
    bad, _r = s.assessed(court, direct_vm, direct_alice, direct_charlie,
                         spec_id="SPEC-000001", pages={s.DOCS_URL: junk}, code="0x",
                         said_by_panel=s.answers(k1="NOT_MET"))
    direct_vm.warp(LATER)
    court.finalize(good)
    court.finalize(bad)
    bob, charlie = s.hexaddr(direct_bob), s.hexaddr(direct_charlie)
    standing = court.get_standing("SPEC-000001", 1, bob, "lumen  KITES", LATER)
    assert standing["found"] and standing["verdict"] == "COMPLIANT"
    assert standing["compliant"] is True and standing["submission_id"] == good
    assert court.is_compliant("SPEC-000001", 1, bob, "Lumen Kites", LATER)["compliant"] is True
    other = court.is_compliant("SPEC-000001", 1, charlie, "Lumen Kites", LATER)
    assert other["compliant"] is False and other["verdict"] == "PARTIALLY_COMPLIANT"
    # a consumer that must choose whose evidence to trust sees both
    listed = court.find_certificates("SPEC-000001", 1, "LUMEN  kites")["submissions"]
    assert [(e["submission_id"], e["submitter"], e["verdict"]) for e in listed] == \
        [(good, bob, "COMPLIANT"), (bad, charlie, "PARTIALLY_COMPLIANT")]
    # nothing under another version, another subject, or for someone who never submitted
    for args in (("SPEC-000001", 2, bob, "Lumen Kites"), ("SPEC-000001", 1, bob, "Other"),
                 ("SPEC-000001", 1, s.hexaddr(direct_alice), "Lumen Kites")):
        assert court.is_compliant(*args, LATER)["compliant"] is False
        assert court.get_standing(*args, LATER)["found"] is False
    assert court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", "soon")["as_of_valid"] \
        is False


def test_a_certificate_expires_when_the_specification_says_so(court, direct_vm, direct_alice,
                                                              direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob,
                                   certificate_ttl=86400)
    direct_vm.warp(LATER)
    court.finalize(submission_id)
    c = court.get_certificate(submission_id, LATER)
    # the lifetime runs from the reading at 12:00, not from the finalize at 13:30
    assert c["compliant"] is True and c["read_at"] == s.NOW
    assert c["valid_until"] == "2026-10-06T12:00:00Z"
    assert court.get_certificate(submission_id, "2026-10-06T12:00:00Z")["compliant"] is True
    late = court.get_certificate(submission_id, "2026-10-06T12:00:01Z")
    assert late["compliant"] is False and late["expired"] is True
    assert late["verdict"] == "COMPLIANT"                # the verdict is history; validity is not
    bob = s.hexaddr(direct_bob)
    assert court.is_compliant("SPEC-000001", 1, bob, "Lumen Kites",
                              "2026-10-07T00:00:00Z") == {
        "compliant": False, "found": True, "verdict": "COMPLIANT",
        "submission_id": submission_id, "expired": True, "spec_retired": False,
        "as_of_valid": True, "not_yet_valid": False}
    assert court.get_certificate(submission_id, "whenever")["compliant"] is False


def test_a_lifetime_runs_from_the_reading_whenever_somebody_finalizes(court, direct_vm,
                                                                      direct_alice, direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob,
                                   certificate_ttl=86400)
    direct_vm.warp("2028-10-05T12:00:00Z")               # nobody finalized for two years
    court.finalize(submission_id)
    c = court.get_certificate(submission_id, "2028-10-05T12:00:00Z")
    assert c["valid_until"] == "2026-10-06T12:00:00Z"
    assert (c["compliant"], c["expired"], c["verdict"]) == (False, True, "COMPLIANT")


def test_a_certificate_says_nothing_about_a_time_before_it_existed(court, direct_vm,
                                                                  direct_alice, direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    court.finalize(submission_id)
    bob = s.hexaddr(direct_bob)
    for early in ("1970-01-01T00:00:00Z", s.NOW, "2026-10-05T13:29:59Z"):
        c = court.get_certificate(submission_id, early)
        assert (c["compliant"], c["not_yet_valid"]) == (False, True), early
        assert court.is_compliant("SPEC-000001", 1, bob, "Lumen Kites", early)["compliant"] \
            is False
    assert court.get_certificate(submission_id, LATER)["compliant"] is True


def test_a_subject_is_submitted_at_most_three_times_and_one_at_a_time(
        court, direct_vm, direct_alice, direct_bob):
    first, _r = s.assessed(court, direct_vm, direct_alice, direct_bob,
                           said_by_panel=s.answers(k1="NOT_MET"))
    # while one is open, the same subject is not submitted again by the same submitter
    with direct_vm.expect_revert("already has a submission of yours that is not yet final"):
        court.submit("SPEC-000001", 1, json.dumps(s.submission("LUMEN  kites")))
    direct_vm.warp(LATER)
    court.finalize(first)
    bob = s.hexaddr(direct_bob)
    assert court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", LATER)["verdict"] == \
        "PARTIALLY_COMPLIANT"
    direct_vm.sender = direct_bob
    second = court.submit("SPEC-000001", 1, json.dumps(s.submission("LUMEN kites")))
    assert court.get_submission(second)["attempt"] == 2
    s.panel(direct_vm, s.answers())
    court.assess(second)
    # the open one is not the standing; the last final one still is
    assert court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", LATER)["submission_id"] \
        == first
    direct_vm.warp("2026-10-05T15:00:00Z")
    court.finalize(second)
    standing = court.get_standing("SPEC-000001", 1, bob, "Lumen Kites",
                                  "2026-10-05T15:00:00Z")
    assert (standing["verdict"], standing["submission_id"], standing["attempts"]) == \
        ("COMPLIANT", second, 2)
    third = court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    s.panel(direct_vm, s.answers(k1="NOT_MET"))
    court.assess(third)
    direct_vm.warp("2026-10-05T17:00:00Z")
    court.finalize(third)
    with direct_vm.expect_revert("has been submitted 3 times under this version"):
        court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    # a later reading replaces the standing, whatever it says
    final = court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", "2026-10-05T17:00:00Z")
    assert (final["verdict"], final["submission_id"], final["attempt"]) == \
        ("PARTIALLY_COMPLIANT", third, 3)


def test_a_submission_nobody_could_read_changes_no_standing(court, direct_vm, direct_alice,
                                                            direct_bob, direct_charlie):
    """A renewal that lapses - the host down, the chain silent, nobody asking -
    says nothing about the subject. It does not replace a certificate that
    rests on a reading; only where there is no standing at all does it stand."""
    first, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    court.finalize(first)
    renewal = court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    direct_vm.clear_mocks()
    s.serve_all(direct_vm, code=None)                     # the issuer's endpoint is silent
    direct_vm.sender = direct_alice
    court.assess(renewal)
    direct_vm.warp("2026-10-05T15:00:00Z")
    court.lapse(renewal)
    bob = s.hexaddr(direct_bob)
    standing = court.get_standing("SPEC-000001", 1, bob, "Lumen Kites", "2026-10-05T15:00:00Z")
    assert (standing["verdict"], standing["submission_id"], standing["compliant"]) == \
        ("COMPLIANT", first, True)
    assert court.get_certificate(renewal, "2026-10-05T15:00:00Z")["verdict"] == "UNVERIFIABLE"
    listed = court.find_certificates("SPEC-000001", 1, "Lumen Kites")["submissions"]
    assert [e["submission_id"] for e in listed] == [first]
    # with no standing at all, the unverifiable one is what there is
    direct_vm.sender = direct_charlie
    only = court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    direct_vm.warp("2026-10-05T17:00:00Z")
    court.lapse(only)
    charlie = s.hexaddr(direct_charlie)
    standing = court.get_standing("SPEC-000001", 1, charlie, "Lumen Kites",
                                  "2026-10-05T17:00:00Z")
    assert (standing["found"], standing["verdict"], standing["compliant"]) == \
        (True, "UNVERIFIABLE", False)


def test_the_order_of_finalizing_cannot_pick_a_standing(court, direct_vm, direct_alice,
                                                        direct_bob, direct_charlie):
    """A stranger cannot make an old attempt the standing by finalizing it last,
    and a submitter cannot keep its best of three by the order of its calls:
    one subject has one open submission at a time, so submissions become final
    in the order they were made."""
    stale = s.submitted(court, direct_vm, direct_alice, direct_bob,
                        pages={s.DOCS_URL: {"body": "x", "status": 503}})
    direct_vm.sender = direct_charlie
    court.assess(stale)                                   # the host is down: nothing read
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("already has a submission of yours that is not yet final: "
                                 + stale):
        court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    # another submitter, and another subject of the same submitter, are not held up
    direct_vm.sender = direct_charlie
    court.submit("SPEC-000001", 1, json.dumps(s.submission()))
    direct_vm.sender = direct_bob
    court.submit("SPEC-000001", 1, json.dumps(s.submission("Another subject")))


def test_names_that_look_alike_are_one_subject(court, direct_vm, direct_alice, direct_bob,
                                               mod):
    first, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.warp(LATER)
    court.finalize(first)
    bob = s.hexaddr(direct_bob)
    cyrillic = "Lumen K" + chr(0x0456) + "tes"
    fullwidth = "Lumen " + "".join(chr(0xFF00 + ord(c) - 0x20) for c in "Kites")
    for spelled in ("lumen   KITES", cyrillic, fullwidth):
        standing = court.get_standing("SPEC-000001", 1, bob, spelled, LATER)
        assert standing["found"] and standing["submission_id"] == first, ascii(spelled)
        assert mod._subject_key(spelled) == "lumen kites"
    # the lookalike spelling counts against the same three submissions
    direct_vm.sender = direct_bob
    again = court.submit("SPEC-000001", 1, json.dumps(s.submission(cyrillic)))
    assert court.get_submission(again)["attempt"] == 2
    # a name carries nothing a reader cannot see
    for hidden in (chr(0x200D), chr(0xFE0F), chr(0xAD), chr(0xE0041), chr(0x0301), chr(1)):
        with direct_vm.expect_revert("subject"):
            court.submit("SPEC-000001", 1,
                         json.dumps(s.submission("Other Kites" + hidden + "x")))


def test_the_views_report_absence(court, direct_vm, direct_alice):
    assert court.get_spec("SPEC-000404", 1)["found"] is False
    assert court.get_spec("SPEC-000404", True)["found"] is False
    assert court.get_spec_versions("SPEC-000404")["found"] is False
    for view in (court.get_submission, court.get_history):
        assert view("SUB-000404")["found"] is False
    assert court.get_certificate("SUB-000404", s.NOW)["found"] is False
    assert court.get_actions("SUB-000404", s.NOW)["found"] is False
    assert court.get_resolution("RD-000404")["found"] is False
    assert court.find_certificates("SPEC-000404", 1, "x")["found"] is False
    for offset, limit in ((0, 51), (-1, 10), (0, 0), (True, 10)):
        page = court.list_submissions(offset, limit)
        assert page["valid"] is False and page["ids"] == []
    config = court.get_config()
    assert config["payable"] == [] and config["contract_version"] == "0.1.0"
    assert config["verdicts"] == ["PENDING", "COMPLIANT", "PARTIALLY_COMPLIANT",
                                  "NON_COMPLIANT", "UNVERIFIABLE"]
    assert "note to the adjudicator" in config["evaluator_markers"]
    assert court.get_stats() == {"specifications": 0, "submissions": 0, "resolutions": 0}


def test_only_final_submissions_are_listed_one_per_submitter(court, direct_vm, direct_alice,
                                                             direct_bob, direct_charlie):
    """Submitting and withdrawing costs nothing, so neither is listed: the
    listing cannot be filled with submissions nobody read."""
    spec_id = s.published(court, direct_vm, direct_alice)
    s.serve_all(direct_vm)
    direct_vm.sender = direct_charlie
    for _round in range(60):
        court.withdraw_submission(court.submit(spec_id, 1, json.dumps(s.submission())))
    assert court.find_certificates(spec_id, 1, "Lumen Kites")["found"] is False
    still_open = court.submit(spec_id, 1, json.dumps(s.submission()))
    assert court.find_certificates(spec_id, 1, "Lumen Kites")["found"] is False
    direct_vm.sender = direct_bob
    first = court.submit(spec_id, 1, json.dumps(s.submission()))
    s.panel(direct_vm, s.answers(k1="NOT_MET"))
    court.assess(first)
    direct_vm.warp(LATER)
    court.finalize(first)
    listed = court.find_certificates(spec_id, 1, "Lumen Kites")["submissions"]
    assert [e["submission_id"] for e in listed] == [first]
    # the same submitter's next final submission takes its place
    second = court.submit(spec_id, 1, json.dumps(s.submission()))
    s.panel(direct_vm, s.answers())
    court.assess(second)
    direct_vm.warp("2026-10-05T15:00:00Z")
    court.finalize(second)
    # a submission no round read is not listed either: filling the listing costs
    # a consensus round for every entry
    court.lapse(still_open)
    listed = court.find_certificates(spec_id, 1, "Lumen Kites")["submissions"]
    assert [(e["submission_id"], e["verdict"]) for e in listed] == [(second, "COMPLIANT")]
    assert court.get_spec(spec_id, 1)["submissions"] == 3   # withdrawn ones are not counted


def test_a_full_listing_makes_way_for_a_reading_and_keeps_the_compliant(
        court, direct_vm, direct_alice, direct_bob, direct_charlie, direct_owner, mod):
    assert mod.MAX_LISTED_PER_SUBJECT == 50
    assert set(mod.READ_REASONS) == {"ASSESSED", "EVIDENCE_GONE_WHILE_CONTESTED"}
    mod.MAX_LISTED_PER_SUBJECT = 2
    try:
        spec_id = s.published(court, direct_vm, direct_alice)
        made = {}
        for who, verdicts in ((direct_bob, s.answers(k1="NOT_MET")),
                              (direct_charlie, s.answers()), (direct_owner, s.answers())):
            direct_vm.clear_mocks()
            made[who], _r = s.assessed(court, direct_vm, direct_alice, who, spec_id=spec_id,
                                       said_by_panel=verdicts)
        direct_vm.warp(LATER)
        for who in (direct_bob, direct_charlie, direct_owner):
            court.finalize(made[who])
        # the entry that is not COMPLIANT made way for the third
        listed = court.find_certificates(spec_id, 1, "Lumen Kites")["submissions"]
        assert [e["submission_id"] for e in listed] == [made[direct_charlie],
                                                        made[direct_owner]]
        # full of COMPLIANT entries: another reading is not listed, and is still a standing
        direct_vm.sender = direct_bob
        again = court.submit(spec_id, 1, json.dumps(s.submission()))
        s.panel(direct_vm, s.answers())
        court.assess(again)
        direct_vm.warp("2026-10-05T15:00:00Z")
        court.finalize(again)
        listed = court.find_certificates(spec_id, 1, "Lumen Kites")["submissions"]
        assert [e["submission_id"] for e in listed] == [made[direct_charlie],
                                                        made[direct_owner]]
        assert court.is_compliant(spec_id, 1, s.hexaddr(direct_bob), "Lumen Kites",
                                  "2026-10-05T15:00:00Z")["compliant"] is True
    finally:
        mod.MAX_LISTED_PER_SUBJECT = 50


def test_a_full_listing_drops_an_expired_certificate_first(
        court, direct_vm, direct_alice, direct_bob, direct_charlie, direct_owner, mod):
    """A lifetime that has run out is not a reason to keep a place: a new
    reading takes it, before any entry that is merely not COMPLIANT."""
    mod.MAX_LISTED_PER_SUBJECT = 2
    try:
        spec_id = s.published(court, direct_vm, direct_alice, certificate_ttl=86400)
        made = {}
        for who, verdicts in ((direct_bob, s.answers()),
                              (direct_charlie, s.answers(k1="NOT_MET"))):
            direct_vm.clear_mocks()
            made[who], _r = s.assessed(court, direct_vm, direct_alice, who, spec_id=spec_id,
                                       said_by_panel=verdicts)
        direct_vm.warp(LATER)
        for who in (direct_bob, direct_charlie):
            court.finalize(made[who])
        # two days on, the first two have expired
        direct_vm.warp("2026-10-07T12:00:00Z")
        direct_vm.clear_mocks()
        made[direct_owner], _r = s.assessed(court, direct_vm, direct_alice, direct_owner,
                                            spec_id=spec_id)
        direct_vm.warp("2026-10-07T13:30:00Z")
        court.finalize(made[direct_owner])
        listed = court.find_certificates(spec_id, 1, "Lumen Kites")["submissions"]
        # the expired COMPLIANT one went - the first in the listing - not the other
        assert [e["submission_id"] for e in listed] == [made[direct_charlie],
                                                        made[direct_owner]]
    finally:
        mod.MAX_LISTED_PER_SUBJECT = 50
