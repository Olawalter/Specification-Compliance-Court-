"""Reads against the canonical StudioNet deployment.

Nothing here asks for a consensus round or changes state. The tests check that
the contract on chain is the contract in this repository, that its surface is
the documented one, and that what the live run recorded is what the registry
still answers through the views a consumer would call.

Each test is independently runnable:

    python -m pytest tests/integration -q
    python -m pytest tests/integration -q -k source_is_this_repository
"""

import base64
import hashlib
import json
import pathlib
import sys
import time
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

RECORD = ROOT / "deploy" / "deployment.json"
TRANSCRIPT = ROOT / "deploy" / "live_run_transcript.json"
CONTRACT = ROOT / "contracts" / "spec_court.py"
CASES = ROOT / "fixtures" / "cases.json"
WALLETS = ROOT / "fixtures" / "wallets.json"
RPC = "https://studio.genlayer.com/api"
WRITES = ("publish_spec", "revise_spec", "retire_version", "submit", "add_mirror",
          "withdraw_submission", "assess", "contest", "finalize", "lapse")
VIEWS = ("get_spec", "get_spec_versions", "get_submission", "get_certificate",
         "get_standing", "is_compliant", "find_certificates", "get_resolution",
         "get_history", "get_actions", "list_specs", "list_submissions", "get_stats",
         "get_config")

pytestmark = pytest.mark.skipif(not RECORD.exists(),
                                reason="no canonical deployment recorded yet")
needs_run = pytest.mark.skipif(not TRANSCRIPT.exists(), reason="no live run recorded yet")


def rpc(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    request = urllib.request.Request(RPC, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "scc-integration"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                answer = json.loads(response.read().decode())
            if "error" in answer and "-32029" in json.dumps(answer["error"]):
                raise RuntimeError("rate limited")
            return answer
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client():
    """A read-only client with a throwaway account: nothing under .data/ is needed."""
    import studionet_transport  # noqa: F401 - retries RPC transport failures
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet
    return create_client(chain=studionet, account=create_account(), endpoint=RPC)


def read(client, record, method, args=None):
    return client.read_contract(address=record["contract_address"],
                                function_name=method, args=args or [])


def steps() -> dict:
    return json.loads(TRANSCRIPT.read_text(encoding="utf-8"))["steps"]


def cases() -> dict:
    return {c["case"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}


def submissions() -> dict:
    """case code -> submission id, for every catalogue case the run submitted."""
    known = cases()
    return {name.split(":", 1)[1]: entry["submission_id"] for name, entry in steps().items()
            if name.startswith("submit:") and name.split(":", 1)[1] in known}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def test_the_deployed_source_is_this_repository(record):
    raw = rpc("gen_getContractCode", [record["contract_address"]]).get("result")
    deployed = str(raw).encode()
    if hashlib.sha256(deployed).hexdigest() != record["source_sha256"]:
        deployed = base64.b64decode(raw)
    assert hashlib.sha256(deployed).hexdigest() == record["source_sha256"]
    assert record["source_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert record["byte_identical"] is True


def test_the_schema_is_the_whole_surface(record):
    schema = rpc("gen_getContractSchema", [record["contract_address"]]).get("result") or {}
    methods = schema.get("methods") or {}
    assert sorted(methods) == sorted(WRITES + VIEWS)
    for name in WRITES:
        assert methods[name].get("payable") in (False, None), name


def test_the_config_on_chain_matches_the_contract(client, record):
    config = read(client, record, "get_config")
    header = CONTRACT.read_text(encoding="utf-8").splitlines()[0]
    assert header == "# v" + config["contract_version"]
    assert config["payable"] == []
    assert config["verdicts"] == ["PENDING", "COMPLIANT", "PARTIALLY_COMPLIANT",
                                  "NON_COMPLIANT", "UNVERIFIABLE"]
    assert config["clause_states"] == ["MET", "NOT_MET"]
    assert config["reading"]["evidence_is_pinned_text"] is True
    assert config["evaluator_markers"]


def test_the_contract_holds_no_money(client, record):
    assert int(client.get_balance(record["contract_address"])) == 0


@needs_run
def test_every_round_the_run_recorded_is_still_on_chain(client, record):
    checked = 0
    for name, entry in sorted(steps().items()):
        if "resolution_id" not in entry:
            continue
        resolution = read(client, record, "get_resolution", [entry["resolution_id"]])
        assert resolution["found"], name
        resolution = resolution["resolution"]
        assert resolution["outcome"] == entry["observed_outcome"], name
        assert resolution["reason_code"] == entry["observed_reason"], name
        assert resolution["states"] == entry["observed_states"], name
        assert resolution["applied"] == entry["applied"], name
        checked += 1
    assert checked > 0


@needs_run
def test_every_case_ended_with_the_verdict_the_catalogue_expects(client, record):
    known = cases()
    as_of = now_iso()
    checked = 0
    for code, submission_id in sorted(submissions().items()):
        case = known[code]
        certificate = read(client, record, "get_certificate", [submission_id, as_of])
        assert certificate["found"] is True, code
        assert certificate["verdict"] == case["expect_verdict"], code
        assert certificate["final_by"] == case["final_by"], code
        if case["path"] == "withdraw":
            assert certificate["status"] == "WITHDRAWN" and not certificate["compliant"], code
        else:
            assert certificate["final"] is True, code
            assert certificate["compliant"] == (case["expect_verdict"] == "COMPLIANT"), code
            if "expect_states" in case:
                assert certificate["states"] == case["expect_states"], code
        checked += 1
    assert checked == len(known)


@needs_run
def test_a_verdict_follows_from_its_mandatory_clauses(client, record):
    spec_id = steps()["publish_spec"]["spec_id"]
    clauses = read(client, record, "get_spec", [spec_id, 1])["spec"]["clauses"]
    mandatory = [c["id"] for c in clauses if c["level"] == "MANDATORY"]
    checked = 0
    for code, submission_id in sorted(submissions().items()):
        certificate = read(client, record, "get_certificate", [submission_id, now_iso()])
        if certificate["final_by"] != "ASSESSED":
            continue
        met = [certificate["states"][c] == "MET" for c in mandatory]
        expected = "COMPLIANT" if all(met) else \
            ("NON_COMPLIANT" if not any(met) else "PARTIALLY_COMPLIANT")
        assert certificate["verdict"] == expected, code
        checked += 1
    assert checked > 0


@needs_run
def test_the_one_boolean_agrees_with_the_certificate(client, record):
    known = cases()
    wallets = json.loads(WALLETS.read_text(encoding="utf-8"))
    as_of = now_iso()
    checked = 0
    for code, submission_id in sorted(submissions().items()):
        case = known[code]
        if case["path"] == "withdraw":
            continue
        certificate = read(client, record, "get_certificate", [submission_id, as_of])
        answer = read(client, record, "is_compliant",
                      [certificate["spec_id"], certificate["version"],
                       wallets[case["submitter"]], case["subject"], as_of])
        assert answer["submission_id"] == submission_id, code
        assert answer["compliant"] == certificate["compliant"], code
        # nobody else's wallet inherits the standing
        other = read(client, record, "is_compliant",
                     [certificate["spec_id"], certificate["version"], wallets["stranger"],
                      case["subject"], as_of])
        assert other["compliant"] is False, code
        checked += 1
    assert checked > 0


@needs_run
def test_every_met_by_the_panel_rests_on_a_passage_of_a_pinned_document(client, record):
    checked = 0
    for name, entry in sorted(steps().items()):
        if "resolution_id" not in entry or not entry.get("applied"):
            continue
        resolution = read(client, record, "get_resolution",
                          [entry["resolution_id"]])["resolution"]
        sources = {s["evidence_id"]: s for s in resolution["sources"]}
        for finding in resolution["findings"]:
            if finding["by"] == "PANEL" and finding["state"] == "MET":
                assert finding["quotes"], name
                for quote in finding["quotes"]:
                    source = sources[quote["evidence_id"]]
                    assert source["raw_sha256"] == source["declared_sha256"], name
                checked += 1
            if finding["by"] == "CODE":
                assert finding["quotes"] == [], name
    assert checked > 0


@needs_run
def test_a_round_that_decided_nothing_changed_nothing(client, record):
    checked = 0
    for name, entry in sorted(steps().items()):
        if entry.get("applied") is not False or "resolution_id" not in entry:
            continue
        resolution = read(client, record, "get_resolution",
                          [entry["resolution_id"]])["resolution"]
        assert resolution["states"] == {} and resolution["markers"] == [], name
        for source in resolution["sources"]:
            assert "raw_sha256" not in source and "title" not in source, name
        checked += 1
    assert checked > 0


@needs_run
def test_only_submissions_a_round_read_are_listed(client, record):
    known = cases()
    spec_id = steps()["publish_spec"]["spec_id"]
    for code, submission_id in sorted(submissions().items()):
        case = known[code]
        listed = read(client, record, "find_certificates", [spec_id, 1, case["subject"]])
        ids = [e["submission_id"] for e in listed.get("submissions", [])]
        assert (submission_id in ids) == (case["final_by"] == "ASSESSED"), code


@needs_run
def test_every_refusal_the_run_recorded_was_for_its_own_reason():
    refusals = [entry for entry in steps().values() if entry.get("kind") == "refusal"]
    assert refusals
    for entry in refusals:
        assert entry["held"] is True, entry["step"]
        assert entry["expect"] in entry["error"], entry["step"]


@needs_run
def test_the_run_of_record_missed_nothing():
    summary = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))["summary"]
    assert summary["missed"] == []
    assert summary["outcomes_held"] == summary["outcomes_checked"] > 0
    assert summary["refusals_held"] == summary["refusals"] > 0
