<p align="center">
  <img src="docs/assets/scc-mark.svg" width="96" height="96" alt="Specification Compliance Court">
</p>

<h1 align="center">Specification Compliance Court</h1>

<p align="center">A public registry of specifications, and of which subjects comply with them.<br>
A standalone GenLayer Intelligent Contract. No frontend, no token, no funds.</p>

## Thesis

A requirement written down before anyone applies is only as good as whoever
reads the applications. This contract lets an issuer publish a specification as
numbered clauses, lets anyone pin evidence for a subject against one version of
it, and has independent validators decide - clause by clause - whether that
evidence substantiates the clause. Code decides everything code can decide.
The result is a certificate another contract can query with one call.

## Canonical deployment

| | |
|---|---|
| Network | GenLayer StudioNet, chain id 61999 |
| Contract | [`0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622`](https://explorer-studio.genlayer.com/address/0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622) |
| Explorer | `https://explorer-studio.genlayer.com/address/0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622` |
| Deployment tx | [`0x5b506b956b08f37cef803bf8e7b82034ef519ddde7849e164341232507121d13`](https://explorer-studio.genlayer.com/tx/0x5b506b956b08f37cef803bf8e7b82034ef519ddde7849e164341232507121d13) |
| Finality / status | FINALIZED, leader execution SUCCESS |
| Consensus result | AGREE x5 |
| Deployment source commit | `3f0ffc8` |
| Current source parity | deployed source read back with `gen_getContractCode`: **byte-identical** to `contracts/spec_court.py` (sha256 `9f80658222c138e429be091fbfde90c0c68e4fea4ded0bcac07dbb557eeaeaee`) |

The full record is [deploy/deployment.json](deploy/deployment.json); how it was
produced is [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## The question

> Given a specification published as numbered clauses before any submission, and
> the evidence a submitter pinned for a named subject, which clauses does the
> evidence substantiate - and so does the subject comply with that version of
> the specification?

The court judges things against specifications. It does not judge people, does
not rank one submission against another, and has no view on whether a
specification is a good one.

## The problem

Grant programmes, hackathons, DAOs, open-source foundations and protocol
standards all publish requirements, and then somebody has to read every
application against them. Today that somebody is the issuer's own reviewer,
reading in private. The applicant cannot see how a clause was read, a third
party cannot rely on the answer, and another contract cannot ask at all.

Half of most requirement lists is mechanical - is the field there, does the
hash match, is there a contract at this address - and the other half is not:
*the documentation states the royalty rate and who can change it* is met or not
by a page of prose.

## Why GenLayer

The mechanical half needs no judgement and gets none: it runs as code inside the
contract, the same on every node. The other half is a reading of a document
against a sentence, and a reading by one party is that party's word. On
GenLayer several validators each fetch the same pinned bytes, read them against
the same published clause with their own model, and refuse a leader whose
answer is well-formed but not what the document supports. What comes out is a
typed result on chain - MET or NOT_MET per clause, with the passage a MET
rests on - not an opinion in an inbox.

## Delete GenLayer: what breaks?

| Without | What is left |
|---|---|
| the model | a checklist runner: it can find a string and call an RPC, and cannot say whether a paragraph states what a clause asks for |
| the validators | one model's reading, chosen by whoever ran it |
| the contract | a requirements page, an application and a private decision |

## Why this is not a rejected pattern

- **Not an oracle.** No feed is relayed. The only outside fact code fetches is
  whether code exists at an address, and that decides only the clause that asks.
- **Not a rubber stamp.** Validators do not check the leader's formatting; each
  re-runs the round from its own fetch and compares what was read and what it
  leads to.
- **Not a score.** There is no number to drift between models. A judged clause
  is MET or NOT_MET, and MET must quote a passage that is in the pinned text.
- **Not a model deciding an outcome.** The model never names a verdict. The
  verdict is derived in code from the clause states by a published rule.
- **Not deterministic work dressed up.** Every check that code can run is a
  `CHECK` clause and never reaches the panel.

## The rule that makes it this contract

**A specification is published once per version, as clauses, and every subject
is judged against the same clauses.** Two subjects with the same clause states
always get the same verdict. Revising a specification makes a new version;
certificates name the version they were issued under and are never carried
over.

## Clauses

A clause is `JUDGED` (prose, read by the panel) or `CHECK` (decided in code),
and `MANDATORY` (decides the verdict) or `OPTIONAL` (reported, never changes
it). A specification has one to eight clauses, at least one mandatory.

| Check | Met when |
|---|---|
| `CONTAINS` / `NOT_CONTAINS` | the document's text has / lacks a passage, word for word |
| `RAW_CONTAINS` / `RAW_NOT_CONTAINS` | the document's source has / lacks an exact string |
| `MIN_WORDS` | the document's text has at least that many words |
| `MAX_BYTES` | the file is no larger than that |
| `VALID_JSON` | the file parses as JSON (`any`, `object` or `array`) |
| `CONTAINS_FIELD` | the document's text names another field of the same submission, or its subject - what binds evidence to the thing it is submitted for |
| `CODE_AT` | a contract exists at the supplied address, on a chain the specification names |

A submission carries the fields the specification asks for: `DOCUMENT` (a
sha256 and one to three addresses that serve those bytes), `ADDRESS`, or
`TEXT`. Evidence is pinned text. A live page that can change is not evidence.

## Verdicts

| Verdict | When |
|---|---|
| `COMPLIANT` | every mandatory clause is met |
| `PARTIALLY_COMPLIANT` | some mandatory clause is met and some is not |
| `NON_COMPLIANT` | no mandatory clause is met |
| `UNVERIFIABLE` | no round could read the evidence, or reach the chain, before the window closed |

The burden is the submitter's: what the evidence does not show is not met.

## Lifecycle and who moves it

```text
publish_spec ─► version 1 ─ revise_spec ─► version 2 ...      retire_version: no new submissions

submit ─► SUBMITTED ─ assess ─► ASSESSED ─ (contest window) ─ finalize ─► FINAL
              │           └ a round that decides nothing is recorded and changes nothing
              ├ withdraw_submission (before any round)
              └ lapse ─► FINAL, UNVERIFIABLE
```

| Step | Who | When |
|---|---|---|
| `publish_spec` / `revise_spec` / `retire_version` | the issuer | any time |
| `submit` | anyone but the issuer | while the version is not retired |
| `add_mirror` | the submitter | until the submission is final |
| `withdraw_submission` | the submitter | before any round has been asked for |
| `assess` | anyone first; retries by the submitter, or by the issuer too when it was the chain or the model that failed | inside the assessment window |
| `contest` | the submitter or the issuer, one read contest each | inside the contest window |
| `finalize` | anyone | after the contest window |
| `lapse` | anyone after the assessment window; the submitter earlier, once a round decided nothing | while no round has read the evidence |

## Contract surface

Ten writes: `publish_spec`, `revise_spec`, `retire_version`, `submit`,
`add_mirror`, `withdraw_submission`, `assess`, `contest`, `finalize`, `lapse`.
Fourteen views: `get_spec`, `get_spec_versions`, `get_submission`,
`get_certificate`, `get_standing`, `is_compliant`, `find_certificates`,
`get_resolution`, `get_history`, `get_actions`, `list_specs`,
`list_submissions`, `get_stats`, `get_config`. Nothing is payable.
[docs/INTEGRATION.md](docs/INTEGRATION.md) describes each.

## Nondeterministic operations

Three, all inside one `run_nondet_unsafe` round per `assess` or `contest`:
fetching each pinned document, asking a named chain endpoint `eth_getCode`, and
one `exec_prompt` over the judged clauses. Nothing else in the contract leaves
deterministic code. [docs/CONSENSUS.md](docs/CONSENSUS.md) has the detail.

## Deterministic responsibilities

Identity and permissions; immutable specification versions and their hashes;
field types and required fields; URL admission and the specification's evidence
hosts; the sha256 pin of every document, checked every round; how bytes become
text; every `CHECK` clause; text addressed to the adjudicator; grounding every
quoted passage in the pinned text; the verdict rule; windows from transaction
time; certificate validity; standing and the listing.

## Equivalence / validator design

A validator does not grade the leader's answer. It runs the same round from its
own fetches and its own model, checks the leader's payload against the
documents it read itself (every quote must be in them, every check is
recomputed), and then compares: what each node could do with each document,
the digest of each text, what each chain answered, the state of every clause,
and the verdict. Any difference is a disagreement, and the reason is printed.

## Safety and failure semantics

| Situation | Rule |
|---|---|
| a document cannot be fetched, or does not match its digest | the round decides nothing; it is recorded and no verdict changes |
| a chain a mandatory clause depends on is silent | the round decides nothing; under an optional clause that clause is simply not met |
| the model's answer is unusable for any judged clause | the round decides nothing |
| nothing reads the evidence before the window ends | `UNVERIFIABLE`, with the reason on the certificate |
| evidence disappears while a favourable verdict is contested | the verdict becomes `UNVERIFIABLE` |
| a document carries text addressed to the adjudicator | every judged clause is not met, without consulting the panel |
| a submission no round could read | it replaces no earlier certificate and is not listed |

## Financial safety, privacy, and no false guarantees

The contract holds no funds and no write is payable. Everything submitted is
public and permanent: do not submit personal data or secrets, and do not put a
key in an RPC address. A certificate says the pinned documents substantiate the
clauses of one specification version. It does not say the documents are true,
that the subject is safe, or that anyone should transact with it. All data in
this repository's fixtures is synthetic and marked as test data.

## Reuse surface

| Consumer | Reads |
|---|---|
| a grant programme or hackathon gating entries | `is_compliant` for the applicant's own submission |
| a DAO or marketplace listing collections, agents or protocols that meet a standard | `find_certificates` and `get_certificate`: each clause's state and what it rests on |
| another contract that must act only for compliant subjects | `get_standing`, with the time it is asking about |

## Limitations

- Evidence is what the submitter pins; the court does not know whether it is true.
- A chain lookup trusts the endpoint the specification names. One that lies is believed.
- A submitter who runs the evidence host can keep any round from reading it; the result is `UNVERIFIABLE`, never a better verdict.
- A verdict can be asked for three times per submitter, subject and version.
- The marker phrases and the lookalike-letter table are tripwires, not complete defences.
- StudioNet is a development network; the deployment is a demonstration.

The full list, with the reasoning, is in [DECISION.md](DECISION.md) and
[docs/SECURITY.md](docs/SECURITY.md).

## Verification

| Check | Result |
|---|---|
| `python -m pytest tests/direct -q` | 122 passed |
| `python scripts/mutation_check.py --jobs 4` | 242 mutations, 242 killed |
| `python -m pytest tests/integration -q` | 13 passed, reading the deployed contract |
| `python scripts/preflight.py` | every check PASS |
| `genvm-lint check contracts/spec_court.py` | ok, 24 methods |
| live run of record | 72 transactions; 46 of 46 outcomes held; 22 of 22 refusals refused for their own reason |

```bash
pip install -r requirements-test.txt
python scripts/fetch_genvm_bundle.py
python -m pytest tests/direct -q
python -m pytest tests/integration -q
python scripts/preflight.py
```

## Reviewer fast path

1. [DECISION.md](DECISION.md) - what the contract decides and refuses to decide, written first.
2. `_node_round`, `_validator_decision` and `_derive` in [contracts/spec_court.py](contracts/spec_court.py) - the round, the comparison and the verdict rule.
3. [docs/CONSENSUS.md](docs/CONSENSUS.md) - what must match between nodes and what may differ.
4. [deploy/live_run_transcript.json](deploy/live_run_transcript.json) - every transaction of the live run and what the chain answered.
5. `python -m pytest tests/integration -q` - reads the deployed contract and checks it against this repository.

## Licence

MIT. Copyright (c) 2026 Olawalter. See [LICENSE](LICENSE).
