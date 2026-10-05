"""Rules that stand behind another rule: each is tested here on its own, so that
removing it is noticed even where a second check would have caught the same
case."""

import json

from tests.direct import support as s

DOWN = {"body": "unavailable", "status": 503, "content_type": "text/plain"}
UNUSABLE = "no comment"


def test_a_final_submission_gives_its_open_slot_back(court, mod, direct_vm, direct_alice,
                                                     direct_bob):
    assert mod.MAX_OPEN_PER_WALLET == 20
    mod.MAX_OPEN_PER_WALLET = 1
    try:
        first, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
        with direct_vm.expect_revert("finish one of your open submissions first"):
            court.submit("SPEC-000001", 1, json.dumps(s.submission(subject="Another Series")))
        direct_vm.warp("2026-10-05T13:30:00Z")
        court.finalize(first)
        direct_vm.sender = direct_bob
        second = court.submit("SPEC-000001", 1,
                              json.dumps(s.submission(subject="Another Series")))
        assert court.get_submission(second)["status"] == "SUBMITTED"
    finally:
        mod.MAX_OPEN_PER_WALLET = 20


def test_a_submitters_free_retry_costs_the_issuer_nothing(court, direct_vm, direct_alice,
                                                         direct_bob):
    """The submitter has paid for two retries that read nothing; its third brings
    the evidence back at a moment the chain is silent. That round is nobody's:
    the issuer still has all three of its own."""
    submission_id, _first = s.assessed(court, direct_vm, direct_alice, direct_bob)
    direct_vm.clear_mocks()
    s.serve_all(direct_vm, {s.DOCS_URL: DOWN})
    direct_vm.sender = direct_alice
    court.contest(submission_id)                         # the issuer's, left open
    direct_vm.sender = direct_bob
    court.contest(submission_id)
    court.contest(submission_id)                         # two dark retries, the submitter's
    direct_vm.clear_mocks()
    s.serve_all(direct_vm, code=None)
    court.contest(submission_id)                         # the evidence is back, the chain silent
    assert court.get_submission(submission_id)["pending_contest"] == ""
    direct_vm.sender = direct_alice
    for _ in range(3):                                   # all three are still the issuer's
        assert court.get_actions(submission_id, s.NOW)["may_contest"]["issuer"] is True
        court.contest(submission_id)
    assert court.get_actions(submission_id, s.NOW)["may_contest"]["issuer"] is False


def test_the_thirteenth_round_is_refused_whoever_asks(court, direct_vm, direct_alice,
                                                      direct_bob):
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob)
    direct_vm.mock_llm("Specification compliance panel", UNUSABLE)
    direct_vm.sender = direct_bob
    court.assess(submission_id)
    direct_vm._llm_mocks.clear()
    s.panel(direct_vm, s.answers())
    court.assess(submission_id)
    for _ in range(5):
        direct_vm.clear_mocks()
        s.serve_all(direct_vm, {s.DOCS_URL: DOWN})
        direct_vm.sender = direct_alice
        court.contest(submission_id)
        direct_vm.clear_mocks()
        s.serve_all(direct_vm)
        direct_vm.mock_llm("Specification compliance panel", UNUSABLE)
        direct_vm.sender = direct_bob
        court.contest(submission_id)
    assert court.get_submission(submission_id)["rounds"] == 12
    # the submitter has every contest round of its own left, and no round to use them in
    with direct_vm.expect_revert("this submission has used its 12 rounds"):
        court.contest(submission_id)


def test_a_verdict_that_rests_on_no_reading_names_no_reading_time(court, direct_vm,
                                                                 direct_alice, direct_bob):
    submission_id, _first = s.assessed(court, direct_vm, direct_alice, direct_bob,
                                       certificate_ttl=30 * 86400)
    assert court.get_certificate(submission_id, s.NOW)["read_at"] == s.NOW
    direct_vm.clear_mocks()
    s.serve_all(direct_vm, {s.DOCS_URL: DOWN})
    direct_vm.sender = direct_alice
    court.contest(submission_id)
    direct_vm.warp("2026-10-05T13:30:00Z")
    assert court.finalize(submission_id) == "UNVERIFIABLE"
    c = court.get_certificate(submission_id, "2026-10-05T13:30:00Z")
    assert (c["final_by"], c["read_at"], c["valid_until"]) == \
        ("EVIDENCE_GONE_WHILE_CONTESTED", "", "")


def test_a_round_that_decides_nothing_stores_no_marker(court, direct_vm, direct_alice,
                                                       direct_bob):
    """The documents were read and one addresses the adjudicator, but the chain
    was silent: the round is not compared end to end, so what the leader says it
    found in the text is not stored."""
    planted = s.page("Lumen Kites documentation",
                     [s.FILLER, s.ROYALTY_LINE, s.CONTRACT_LINE, s.INJECTION])
    submission_id = s.submitted(court, direct_vm, direct_alice, direct_bob,
                                pages={s.DOCS_URL: planted}, code=None)
    direct_vm.sender = direct_bob
    record = s.record_of(court, court.assess(submission_id))
    assert record["reason_code"] == "CHAIN_UNREACHABLE" and record["applied"] is False
    assert s.leader_payload(direct_vm)["markers"] != []
    assert record["markers"] == []


def test_an_error_that_is_null_is_no_error(court, mod, direct_vm):
    answer = {"jsonrpc": "2.0", "id": 1, "result": "0x6080", "error": None}
    s.chain(direct_vm, raw=json.dumps(answer))
    assert mod._code_at(s.RPC_URL, s.COLLECTION) == "CODE"
    direct_vm.clear_mocks()
    s.chain(direct_vm, raw=json.dumps(dict(answer, error="")))
    assert mod._code_at(s.RPC_URL, s.COLLECTION) == "UNREACHABLE"


def test_a_lookup_in_a_payload_is_the_one_the_clause_calls_for(mod, court):
    ctx = {"spec": s.spec(), "values": {"contract": s.COLLECTION}}
    needed = mod._lookups_needed(ctx)[0]
    good = {"clause": needed["clause"], "chain": needed["chain"],
            "address": needed["address"], "result": "CODE"}
    assert mod._valid_lookups([good], ctx) is True
    for key, value in (("clause", "k3"), ("chain", "elsewhere"),
                       ("address", "0x" + "ab" * 20)):
        assert mod._valid_lookups([dict(good, **{key: value})], ctx) is False, key
    for result in ("EMPTY", "UNREACHABLE", "NOT_ASKED"):
        assert mod._valid_lookups([dict(good, result=result)], ctx) is True
    for result in ("", "code", "YES", None, 1, True, ["CODE"]):
        assert mod._valid_lookups([dict(good, result=result)], ctx) is False, result
    assert mod._valid_lookups([], ctx) is False
    assert mod._valid_lookups([good, good], ctx) is False


def test_a_title_that_cannot_be_encoded_fails_the_gate(court, mod, direct_vm, direct_alice,
                                                       direct_bob):
    submission_id, _r = s.assessed(court, direct_vm, direct_alice, direct_bob)
    payload = s.leader_payload(direct_vm)
    ctx = court._ctx(court.submissions.get(submission_id), "ASSESS", s.NOW)
    ctx["round"] = 1
    assert mod._parse_payload(json.dumps(payload), ctx) is not None
    payload["sources"][0]["title"] = payload["sources"][0]["title"] + chr(0xD800)
    assert mod._parse_payload(json.dumps(payload), ctx) is None


def test_nodes_that_differ_on_why_a_round_decided_nothing_disagree(mod, court):
    mine = {"panel_reason": "EVIDENCE_UNREADABLE"}
    for theirs in ("", "CHAIN_UNREACHABLE", "SOURCE_ADDRESSES_ADJUDICATOR"):
        assert mod._evidence_difference({"items": []}, mine, {"panel_reason": theirs}) != ""
    assert mod._evidence_difference({"items": []}, mine, dict(mine)) == ""
