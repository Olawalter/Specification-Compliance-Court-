#!/usr/bin/env python3
"""Drive the deployed contract through every path with real transactions, and
record what the chain answered.

    python scripts/live_run.py <address> --raw-base <pinned raw url> --phase full

Phases run in order and can be run one at a time: publish, submit, assess,
finalize, versions, refusals, registry. Every step is recorded in
deploy/live_run_transcript.json under a unique name; re-running skips steps
already recorded, so a transport failure or a rate limit never repeats work. A
step whose write reverted is retried on a resume.

The evidence is served at a pinned commit from this repository, by the raw host
and by its CDN mirror; the bytes are what each submission's sha256 was taken
over. The chain lookups ask a public endpoint the specification names.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import studionet_transport  # noqa: E402,F401 - retries RPC transport failures
from genlayer_py import create_account, create_client  # noqa: E402
from genlayer_py.chains import studionet  # noqa: E402
from genlayer_py.types import TransactionStatus  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
KEYS = ROOT / ".data" / "demo_wallets.json"
TRANSCRIPT = ROOT / "deploy" / "live_run_transcript.json"
LOG = ROOT / "deploy" / "live_run.log"
RPC = "https://studio.genlayer.com/api"
WAIT = dict(interval=5000, retries=300)
PHASES = ("publish", "submit", "assess", "finalize", "versions", "refusals", "registry")


def log(text: str):
    line = time.strftime("%H:%M:%S") + " " + text
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def now_iso(offset: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


def epoch(iso: str) -> float:
    return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone


def wait_until(iso: str, what: str):
    target = epoch(iso)
    while True:
        left = target - time.time()
        if left <= -3:                 # past the moment, never a few seconds short of it
            return
        log("  waiting " + str(int(left) + 5) + "s for " + what)
        time.sleep(min(left + 5, 120))


# -- the transcript ------------------------------------------------------------

class Transcript:
    def __init__(self, address: str, raw_base: str, path=None):
        self.path = path or TRANSCRIPT
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"address": address, "raw_base": raw_base,
                         "started_at": now_iso(), "steps": {}, "order": []}
        if self.data["address"] != address:
            sys.exit("the transcript records a different contract; move it aside first")
        self.data["raw_base"] = raw_base

    def has(self, step: str) -> bool:
        return step in self.data["steps"]

    def done(self, step: str) -> bool:
        return self.has(step) and self.get(step).get("leader_execution") == "SUCCESS"

    def get(self, step: str) -> dict:
        return self.data["steps"][step]

    def put(self, step: str, entry: dict):
        entry["at"] = now_iso()
        entry["step"] = step
        if step not in self.data["steps"]:
            self.data["order"].append(step)
        self.data["steps"][step] = entry
        self.save()

    def save(self):
        self.data["finished_at"] = now_iso()
        self.data["summary"] = self.summary()
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")

    def summary(self) -> dict:
        steps = self.data["steps"].values()
        checks = [s for s in steps if "held" in s and s.get("kind") != "refusal"]
        refusals = [s for s in steps if s.get("kind") == "refusal"]
        return {
            "steps": len(self.data["order"]),
            "transactions": len([s for s in steps if s.get("tx")]),
            "outcomes_checked": len(checks),
            "outcomes_held": len([s for s in checks if s["held"]]),
            "missed": sorted(s["step"] for s in checks if not s["held"]),
            "refusals": len(refusals),
            "refusals_held": len([s for s in refusals if s.get("held")]),
        }


def _hex(value) -> str:
    return value if isinstance(value, str) else "0x" + bytes(value).hex()


def _plain(args) -> list:
    out = []
    for value in args:
        text = value if isinstance(value, (str, int, bool)) else str(value)
        if isinstance(text, str) and len(text) > 200:
            text = text[:200] + "... (" + str(len(text)) + " characters)"
        out.append(text)
    return out


def _status(receipt) -> str:
    for key in ("status", "statusName", "status_name"):
        value = receipt.get(key)
        if isinstance(value, str):
            return value
        if value is not None and hasattr(value, "name"):
            return value.name
    return "UNKNOWN"


def _leader(receipt) -> dict:
    data = receipt.get("consensus_data") or {}
    leader = data.get("leader_receipt") or {}
    if isinstance(leader, list):
        leader = leader[0] if leader else {}
    return leader


def _execution(receipt) -> str:
    value = _leader(receipt).get("execution_result")
    return value if isinstance(value, str) else str(value)


def _revert(receipt) -> str:
    result = _leader(receipt).get("result") or {}
    return json.dumps(result)[:400] if not isinstance(result, str) else result[:400]


def _votes(receipt) -> list:
    last = receipt.get("last_round") or {}
    votes = last.get("votes") or (receipt.get("consensus_data") or {}).get("votes") or {}
    if isinstance(votes, dict):
        return [str(v) for v in votes.values()]
    return [str(v) for v in votes]


# -- the chain -----------------------------------------------------------------

class Chain:
    def __init__(self, address: str, transcript: Transcript):
        self.address = address
        self.transcript = transcript
        self.raw_base = transcript.data["raw_base"]
        keys = json.loads(KEYS.read_text(encoding="utf-8"))
        self.accounts = {name: create_account(account_private_key=key)
                         for name, key in keys.items()}
        self.clients = {name: create_client(chain=studionet, account=account,
                                            endpoint=RPC)
                        for name, account in self.accounts.items()}
        self.reader = self.clients[sorted(self.clients)[0]]

    def address_of(self, wallet: str) -> str:
        return str(self.accounts[wallet].address).lower()

    def read(self, method: str, args=None):
        return self.reader.read_contract(address=self.address, function_name=method,
                                         args=args or [])

    def send(self, step: str, wallet: str, method: str, args=None) -> dict:
        if self.transcript.has(step):
            entry = self.transcript.get(step)
            if entry.get("leader_execution") == "SUCCESS":
                log("  skip " + step + " (recorded " + entry.get("status", "?") + ")")
                return entry
            log("  retry " + step + " (recorded " + str(entry.get("error"))[:80] + ")")
        client = self.clients[wallet]
        log("  " + step + ": " + method + " as " + wallet)
        tx = client.write_contract(address=self.address, function_name=method,
                                   args=args or [])
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=tx, status=TransactionStatus.FINALIZED, **WAIT)
        entry = {"kind": "write", "method": method, "wallet": wallet,
                 "args": _plain(args or []), "tx": _hex(tx),
                 "status": _status(receipt), "leader_execution": _execution(receipt),
                 "votes": _votes(receipt), "result": _revert(receipt)}
        if entry["leader_execution"] != "SUCCESS":
            entry["error"] = _revert(receipt)
        self.transcript.put(step, entry)
        log("    " + entry["status"] + "/" + entry["leader_execution"] + " votes "
            + ",".join(entry["votes"]))
        return entry

    def must(self, step: str, wallet: str, method: str, args=None) -> dict:
        entry = self.send(step, wallet, method, args)
        if entry.get("leader_execution") != "SUCCESS":
            raise SystemExit("  " + step + " did not execute: " + str(entry.get("error")))
        return entry

    def refuse(self, step: str, wallet: str, method: str, args=None, because: str = "",
               expect: str = "") -> dict:
        """A write that must be refused - and for the reason it was sent to test:
        a refusal for some other reason is recorded as a miss."""
        if self.transcript.has(step):
            log("  skip " + step + " (recorded)")
            return self.transcript.get(step)
        client = self.clients[wallet]
        log("  " + step + ": expecting a refusal of " + method)
        entry = {"kind": "refusal", "method": method, "wallet": wallet,
                 "args": _plain(args or []), "because": because, "expect": expect}
        try:
            tx = client.write_contract(address=self.address, function_name=method,
                                       args=args or [])
            receipt = client.wait_for_transaction_receipt(
                transaction_hash=tx, status=TransactionStatus.FINALIZED, **WAIT)
            entry["tx"] = _hex(tx)
            entry["status"] = _status(receipt)
            entry["leader_execution"] = _execution(receipt)
            entry["error"] = _revert(receipt)
            entry["held"] = entry["leader_execution"] != "SUCCESS"
        except Exception as err:                       # a client-side rejection counts
            entry["error"] = str(err)[:400]
            entry["held"] = True
        if entry["held"] and expect not in str(entry.get("error", "")):
            entry["held"] = False
            entry["wrong_reason"] = True
        self.transcript.put(step, entry)
        log("    refused" if entry["held"] else
            ("    REFUSED FOR ANOTHER REASON - recorded as a miss" if entry.get("wrong_reason")
             else "    NOT REFUSED - recorded as a miss"))
        return entry

    def check(self, step: str, held: bool, **fields):
        entry = self.transcript.get(step) if self.transcript.has(step) else {"kind": "check"}
        entry.update(fields)
        entry["held"] = bool(held)
        self.transcript.put(step, entry)
        log("    " + step + (" HELD" if held else " MISSED") + " "
            + json.dumps({k: v for k, v in fields.items() if k != "note"})[:200])


# -- the catalogue -------------------------------------------------------------

def mirror(raw_base: str) -> str:
    prefix = "https://raw.githubusercontent.com/"
    if not raw_base.startswith(prefix):
        sys.exit("--raw-base must be a commit-pinned raw.githubusercontent.com URL")
    owner, repo, commit, rest = raw_base[len(prefix):].split("/", 3)
    return "https://cdn.jsdelivr.net/gh/" + owner + "/" + repo + "@" + commit + "/" + rest


def addresses(how: str, document: str, base: str, raw_base: str, unpublished: str) -> list:
    """Where a document is served from. `both`: the CDN mirror and the raw host,
    the same pinned bytes at two addresses. `dead_then_live`: an address that
    serves nothing, then one that serves the document. `dead`: only the address
    that serves nothing."""
    live = [base + document, raw_base + document]
    dead = base + unpublished + "?for=" + document.rsplit("/", 1)[-1]
    return {"both": live, "dead_then_live": [dead, live[1]], "dead": [dead]}[how]


def submission_of(case: dict, base: str, raw_base: str, unpublished: str) -> str:
    fields = {}
    for field, entry in case["documents"].items():
        fields[field] = {"sha256": entry["sha256"],
                         "urls": addresses(case["addresses"], entry["document"], base,
                                           raw_base, unpublished)}
    fields.update(case["values"])
    return json.dumps({"subject": case["subject"], "fields": fields}, sort_keys=True)


def submission_id_of(chain: Chain, code: str) -> str:
    return chain.transcript.get("submit:" + code)["submission_id"]


def newest_submission(chain: Chain, wallet: str) -> str:
    total = chain.read("get_stats")["submissions"]
    submission_id = chain.read("list_submissions", [total - 1, 1])["ids"][0]
    if chain.read("get_submission", [submission_id])["submitter"] != chain.address_of(wallet):
        raise SystemExit("  the newest submission is not this submitter's")
    return submission_id


def submit(chain: Chain, code: str, wallet: str, spec_id: str, version: int,
           payload: str) -> str:
    step = "submit:" + code
    entry = chain.must(step, wallet, "submit", [spec_id, version, payload])
    if "submission_id" not in entry:
        entry["submission_id"] = newest_submission(chain, wallet)
        chain.transcript.put(step, entry)
    return entry["submission_id"]


def spec_id_of(chain: Chain) -> str:
    return chain.transcript.get("publish_spec")["spec_id"]


# -- the phases ----------------------------------------------------------------

def phase_publish(chain: Chain, cases: dict, template: dict):
    entry = chain.must("publish_spec", "issuer", "publish_spec",
                       [json.dumps(template, sort_keys=True)])
    if "spec_id" not in entry:
        total = chain.read("get_stats")["specifications"]
        entry["spec_id"] = chain.read("list_specs", [total - 1, 1])["ids"][0]
        chain.transcript.put("publish_spec", entry)
    spec_id = entry["spec_id"]
    got = chain.read("get_spec", [spec_id, 1])
    chain.check("publish_spec", got["found"] and got["issuer"] == chain.address_of("issuer")
                and got["version"] == 1 and got["retired"] is False,
                spec_id=spec_id, spec_hash=got["spec_hash"])


def phase_submit(chain: Chain, cases: dict, base: str, raw_base: str):
    spec_id = spec_id_of(chain)
    for case in cases["cases"]:
        payload = "" if chain.transcript.has("submit:" + case["case"]) else \
            submission_of(case, base, raw_base, cases["unpublished"])
        submission_id = submit(chain, case["case"], case["submitter"], spec_id, 1, payload)
        got = chain.read("get_submission", [submission_id])
        chain.check("submit:" + case["case"], got["status"] in ("SUBMITTED", "ASSESSED",
                                                               "FINAL", "WITHDRAWN")
                    and got["subject"] == case["subject"], subject=got["subject"])


def record_round(chain: Chain, step: str, submission_id: str, case: dict, expect: str,
                 upheld: bool = False):
    history = chain.read("get_history", [submission_id])["rounds"]
    resolution = chain.read("get_resolution", [history[-1]["resolution_id"]])["resolution"]
    entry = chain.transcript.get(step)
    entry.update(resolution_id=resolution["resolution_id"], round=resolution["round"],
                 applied=resolution["applied"], observed_outcome=resolution["outcome"],
                 observed_reason=resolution["reason_code"],
                 observed_states=resolution["states"], panel_state=resolution["panel_state"],
                 lookups=resolution["lookups"], markers=resolution["markers"],
                 served_by=[x.get("served_by", "") for x in resolution["sources"]],
                 note=case["note"])
    chain.transcript.put(step, entry)
    if expect == "unread":
        state = chain.read("get_submission", [submission_id])
        held = resolution["applied"] is False \
            and resolution["reason_code"] == case["expect_round"] \
            and state["status"] == "SUBMITTED" \
            and state["open_round"] == "EVIDENCE_UNREADABLE"
        chain.check(step, held, expected="recorded, not applied, the submission stays open",
                    status_after=state["status"], open_round=state["open_round"])
        return
    held = resolution["applied"] is True \
        and resolution["states"] == case["expect_states"] \
        and resolution["outcome"] == case["expect_verdict"]
    if "expect_reason" in case:
        held = held and resolution["reason_code"] == case["expect_reason"]
    if upheld:
        held = held and resolution["round"] == 2
    if case.get("expect_served_by") == "raw":
        held = held and all(url.startswith(chain.raw_base) for url in entry["served_by"])
    chain.check(step, held, expected_states=case["expect_states"],
                expected_verdict=case["expect_verdict"])


def phase_assess(chain: Chain, cases: dict, raw_base: str):
    for case in cases["cases"]:
        code = case["case"]
        submission_id = submission_id_of(chain, code)
        if case["path"] == "withdraw":
            chain.must("withdraw:" + code, case["submitter"], "withdraw_submission",
                       [submission_id])
            got = chain.read("get_certificate", [submission_id, now_iso()])
            chain.check("withdraw:" + code, got["status"] == "WITHDRAWN"
                        and got["compliant"] is False, status=got["status"])
            continue
        step = "assess:" + code
        if case["path"] == "mirror_added":
            # a round that cannot fetch the evidence, an address added, a round that can
            first = "assess-unread:" + code
            if not chain.transcript.done(first):
                chain.must(first, "keeper", "assess", [submission_id])
            if "held" not in chain.transcript.get(first):
                record_round(chain, first, submission_id, case, "unread")
            for field, entry in case["documents"].items():
                chain.must("add_mirror:" + code + ":" + field, case["submitter"],
                           "add_mirror", [submission_id, field, raw_base + entry["document"]])
            if not chain.transcript.done(step):
                chain.must(step, case["submitter"], "assess", [submission_id])
        elif not chain.transcript.done(step):
            chain.must(step, "keeper", "assess", [submission_id])
        if "held" not in chain.transcript.get(step):
            record_round(chain, step, submission_id, case,
                         "unread" if case["path"] in ("unreadable", "given_up") else "read")
        if case.get("contest"):
            step = "contest:" + code
            if not chain.transcript.done(step):
                chain.must(step, case["contest"], "contest", [submission_id])
            if "held" not in chain.transcript.get(step):
                record_round(chain, step, submission_id, case, "read", upheld=True)


def final_check(chain: Chain, step: str, submission_id: str, case: dict):
    as_of = now_iso()
    certificate = chain.read("get_certificate", [submission_id, as_of])
    standing = chain.read("is_compliant", [certificate["spec_id"], certificate["version"],
                                           chain.address_of(case["submitter"]),
                                           case["subject"].upper(), as_of])
    held = certificate["final"] is True \
        and certificate["verdict"] == case["expect_verdict"] \
        and certificate["final_by"] == case["final_by"] \
        and certificate["compliant"] == (case["expect_verdict"] == "COMPLIANT") \
        and standing["compliant"] == certificate["compliant"] \
        and standing["submission_id"] == submission_id
    chain.check(step, held, verdict=certificate["verdict"], final_by=certificate["final_by"],
                compliant=certificate["compliant"], tally=certificate["tally"],
                note=case["note"])


def phase_finalize(chain: Chain, cases: dict):
    for case in cases["cases"]:
        code = case["case"]
        if case["path"] == "withdraw":
            continue
        submission_id = submission_id_of(chain, code)
        state = chain.read("get_submission", [submission_id])
        if case["path"] == "given_up":
            # nobody else closes it before the window; its submitter may
            step = "lapse:" + code
            chain.refuse("refuse:lapse_early_by_another", "keeper", "lapse", [submission_id],
                         because="only the submitter gives a submission up early",
                         expect="the assessment window closes at")
            if not chain.transcript.done(step):
                chain.must(step, case["submitter"], "lapse", [submission_id])
        elif case["path"] == "unreadable":
            step = "lapse:" + code
            if not chain.transcript.done(step):
                wait_until(state["window_ends"], "the assessment window of " + submission_id)
                chain.must(step, "keeper", "lapse", [submission_id])
        else:
            step = "finalize:" + code
            if not chain.transcript.done(step):
                wait_until(state["window_ends"], "the contest window of " + submission_id)
                chain.must(step, "keeper", "finalize", [submission_id])
        final_check(chain, step, submission_id, case)


def phase_versions(chain: Chain, cases: dict, template: dict, base: str, raw_base: str):
    """A revision is a new version; certificates name their version and are not
    carried over; a retired version takes no new submissions."""
    spec_id = spec_id_of(chain)
    revised = json.loads(json.dumps(template))
    revised["certificate_ttl"] = 30 * 86400
    chain.refuse("refuse:revise_by_stranger", "stranger", "revise_spec",
                 [spec_id, json.dumps(revised, sort_keys=True)],
                 because="only the issuer revises its specification",
                 expect="only the issuer revises")
    chain.must("revise_spec", "issuer", "revise_spec",
               [spec_id, json.dumps(revised, sort_keys=True)])
    versions = chain.read("get_spec_versions", [spec_id])
    first = cases["cases"][0]
    as_of = now_iso()
    under_two = chain.read("is_compliant", [spec_id, 2, chain.address_of(first["submitter"]),
                                            first["subject"], as_of])
    under_one = chain.read("is_compliant", [spec_id, 1, chain.address_of(first["submitter"]),
                                            first["subject"], as_of])
    chain.check("revise_spec", versions["latest_version"] == 2
                and under_one["compliant"] is True and under_two["found"] is False
                and under_two["compliant"] is False,
                latest_version=versions["latest_version"], v1=under_one["compliant"],
                v2_found=under_two["found"])
    # the same subject, submitted again under version 2: its certificate has a lifetime
    again = dict(first, case="V2")
    payload = "" if chain.transcript.has("submit:V2") else \
        submission_of(again, base, raw_base, cases["unpublished"])
    submission_id = submit(chain, "V2", first["submitter"], spec_id, 2, payload)
    if not chain.transcript.done("assess:V2"):
        chain.must("assess:V2", "keeper", "assess", [submission_id])
    if "held" not in chain.transcript.get("assess:V2"):
        record_round(chain, "assess:V2", submission_id, first, "read")
    step = "finalize:V2"
    if not chain.transcript.done(step):
        state = chain.read("get_submission", [submission_id])
        wait_until(state["window_ends"], "the contest window of " + submission_id)
        chain.must(step, "keeper", "finalize", [submission_id])
    certificate = chain.read("get_certificate", [submission_id, now_iso()])
    far = chain.read("get_certificate", [submission_id, now_iso(31 * 86400)])
    chain.check(step, certificate["compliant"] is True and certificate["version"] == 2
                and certificate["valid_until"] != "" and far["compliant"] is False
                and far["expired"] is True and far["verdict"] == "COMPLIANT",
                valid_until=certificate["valid_until"], expired_later=far["expired"])
    chain.refuse("refuse:retire_by_stranger", "stranger", "retire_version", [spec_id, 1],
                 because="only the issuer retires a version",
                 expect="only the issuer retires")
    chain.must("retire_version", "issuer", "retire_version", [spec_id, 1])
    kept = chain.read("get_certificate", [submission_id_of(chain, first["case"]), now_iso()])
    chain.check("retire_version", kept["compliant"] is True and kept["spec_retired"] is True,
                compliant=kept["compliant"], spec_retired=kept["spec_retired"])
    late = dict(first, case="LATE", subject="A late subject (test only)")
    chain.refuse("refuse:submit_to_retired", first["submitter"], "submit",
                 [spec_id, 1, submission_of(late, base, raw_base, cases["unpublished"])],
                 because="a retired version takes no new submissions",
                 expect="retired and takes no new submissions")


def phase_refusals(chain: Chain, cases: dict, template: dict, base: str, raw_base: str):
    spec_id = spec_id_of(chain)
    by_code = {c["case"]: c for c in cases["cases"]}
    sample = by_code["SC02"]
    final = submission_id_of(chain, "SC02")
    payload = json.loads(submission_of(dict(sample, subject="A refused subject (test only)"),
                                       base, raw_base, cases["unpublished"]))

    def changed(**fields):
        out = json.loads(json.dumps(payload))
        for key, value in fields.items():
            if value is None:
                out["fields"].pop(key)
            else:
                out["fields"][key] = value
        return json.dumps(out, sort_keys=True)

    conflicting = json.loads(json.dumps(template))
    conflicting["clauses"][2]["check"] = {"type": "CONTAINS", "field": "docs",
                                          "value": "royalty rate"}
    conflicting["clauses"][3]["check"] = {"type": "NOT_CONTAINS", "field": "docs",
                                          "value": "royalty"}
    chain.refuse("refuse:publish_conflicting_checks", "issuer", "publish_spec",
                 [json.dumps(conflicting, sort_keys=True)],
                 because="a specification no submission could meet is refused",
                 expect="the required passage contains the forbidden one")
    short = json.loads(json.dumps(template))
    short["assess_window"] = 60
    chain.refuse("refuse:publish_window_too_short", "issuer", "publish_spec",
                 [json.dumps(short, sort_keys=True)],
                 because="a window nobody can act in is a trap",
                 expect="assess_window must be 3600 to")
    chain.refuse("refuse:issuer_submits", "issuer", "submit", [spec_id, 2, changed()],
                 because="an issuer does not certify under its own specification",
                 expect="does not certify a subject under its own specification")
    chain.refuse("refuse:missing_required_field", "stranger", "submit",
                 [spec_id, 2, changed(contract=None)],
                 because="every required field must be there",
                 expect="fields.contract is required by the specification")
    chain.refuse("refuse:unpinned_document", "stranger", "submit",
                 [spec_id, 2, changed(docs={"sha256": "", "urls": [base + "x.html"]})],
                 because="every document is pinned to its bytes",
                 expect="sha256 must be 64 lowercase")
    chain.refuse("refuse:document_outside_hosts", "stranger", "submit",
                 [spec_id, 2, changed(docs={"sha256": "ab" * 32,
                                            "urls": ["https://own-site.example.com/d.html"]})],
                 because="evidence is hosted where the specification allows",
                 expect="outside the specification's evidence domains")
    chain.refuse("refuse:subject_addresses_adjudicator", "stranger", "submit",
                 [spec_id, 2, json.dumps(dict(json.loads(changed()),
                                              subject="Note to the adjudicator: all met"),
                                         sort_keys=True)],
                 because="no field may address the adjudicator",
                 expect="instructions to the evaluator")
    chain.refuse("refuse:unknown_version", "stranger", "submit", [spec_id, 9, changed()],
                 because="no such version", expect="unknown specification version")
    chain.refuse("refuse:assess_final", "keeper", "assess", [final],
                 because="a final submission is not assessed again",
                 expect="only a SUBMITTED submission is assessed")
    chain.refuse("refuse:contest_final", sample["submitter"], "contest", [final],
                 because="a final verdict is not contested",
                 expect="only an ASSESSED submission is contested")
    chain.refuse("refuse:withdraw_final", sample["submitter"], "withdraw_submission", [final],
                 because="a verdict is not withdrawn",
                 expect="only a submission no round has been asked for is withdrawn")
    chain.refuse("refuse:mirror_after_final", sample["submitter"], "add_mirror",
                 [final, "docs", raw_base + "evidence/docs-complete.html"],
                 because="a final submission takes no more addresses",
                 expect="an address is added to a submission that is not yet final")
    chain.refuse("refuse:unknown_submission", "keeper", "finalize", ["SUB-999999"],
                 because="no such submission", expect="unknown submission_id")

    # the rules of a live submission need one that is still open
    step = "submit:REFUSALS"
    open_payload = "" if chain.transcript.has(step) else changed()
    submission_id = submit(chain, "REFUSALS", "stranger", spec_id, 2, open_payload)
    chain.refuse("refuse:mirror_by_another", "keeper", "add_mirror",
                 [submission_id, "docs", raw_base + "evidence/docs-complete.html"],
                 because="only the submitter says where its evidence is served",
                 expect="only the submitter adds an address")
    chain.refuse("refuse:withdraw_by_another", "keeper", "withdraw_submission",
                 [submission_id], because="only the submitter withdraws",
                 expect="only the submitter withdraws")
    chain.refuse("refuse:lapse_too_early", "keeper", "lapse", [submission_id],
                 because="a submission lapses only after its window",
                 expect="the assessment window closes at")
    if not chain.transcript.done("assess:REFUSALS"):
        chain.must("assess:REFUSALS", "keeper", "assess", [submission_id])
    chain.refuse("refuse:contest_by_stranger", "keeper", "contest", [submission_id],
                 because="only the submitter or the issuer contests",
                 expect="only the submitter or the issuer contests")
    chain.refuse("refuse:finalize_too_early", "keeper", "finalize", [submission_id],
                 because="a verdict is final only after its contest window",
                 expect="the contest window closes at")


def phase_registry(chain: Chain, cases: dict):
    """What a consumer reads, checked against what the run did."""
    spec_id = spec_id_of(chain)
    stats = chain.read("get_stats")
    config = chain.read("get_config")
    first = cases["cases"][0]
    listed = chain.read("find_certificates", [spec_id, 1, first["subject"]])
    chain.check("registry", config["payable"] == [] and stats["specifications"] >= 1
                and listed["found"] is True
                and submission_id_of(chain, first["case"]) in
                [e["submission_id"] for e in listed["submissions"]],
                specifications=stats["specifications"], submissions=stats["submissions"],
                resolutions=stats["resolutions"])
    chain.transcript.data["stats"] = stats
    chain.transcript.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--raw-base", required=True)
    parser.add_argument("--phase", default="full", choices=PHASES + ("full",))
    parser.add_argument("--transcript", default="")
    args = parser.parse_args()
    path = None
    if args.transcript:
        path = pathlib.Path(args.transcript)
        path.parent.mkdir(parents=True, exist_ok=True)
        globals()["LOG"] = path.with_suffix(".log")
    raw_base = args.raw_base if args.raw_base.endswith("/") else args.raw_base + "/"
    transcript = Transcript(args.address, raw_base, path)
    template = json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8"))
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    base = mirror(raw_base)
    chain = Chain(args.address, transcript)
    log("contract " + args.address + " phase " + args.phase)
    phases = PHASES if args.phase == "full" else (args.phase,)
    for phase in phases:
        log("phase " + phase)
        if phase == "publish":
            phase_publish(chain, cases, template)
        elif phase == "submit":
            phase_submit(chain, cases, base, raw_base)
        elif phase == "assess":
            phase_assess(chain, cases, raw_base)
        elif phase == "finalize":
            phase_finalize(chain, cases)
        elif phase == "versions":
            phase_versions(chain, cases, template, base, raw_base)
        elif phase == "refusals":
            phase_refusals(chain, cases, template, base, raw_base)
        elif phase == "registry":
            phase_registry(chain, cases)
    log("summary " + json.dumps(transcript.summary()))


if __name__ == "__main__":
    main()
