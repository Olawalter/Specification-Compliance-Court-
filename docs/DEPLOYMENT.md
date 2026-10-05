# Deployment

Where the contract is, how to reproduce the deployment, and what was run
against it.

## Environment

| | |
|---|---|
| Network | GenLayer StudioNet, chain id 61999 |
| RPC | `https://studio.genlayer.com/api` |
| Explorer | `https://explorer-studio.genlayer.com` |
| Runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`, pinned in the contract's first lines |
| Toolchain | Python 3.12; versions pinned in `requirements.txt` and `requirements-test.txt` |

StudioNet is gasless and the contract holds no funds: no key in this
repository's workflow controls anything of value. Keys live in `.data/`, which
is gitignored.

## Reproduce

```bash
pip install -r requirements-test.txt
python scripts/fetch_genvm_bundle.py
python -m pytest tests/direct -q
python scripts/deploy_studionet.py --disposable
```

`deploy_studionet.py` refuses to deploy a contract file that is not committed
and unmodified, waits for FINALIZED, requires the leader's execution result to
be SUCCESS, reads the deployed source back with `gen_getContractCode` and
compares its sha256 with the file in the tree. `--verify` re-checks the
recorded deployment; `--disposable` records under `deploy/diagnostics/`.

## Canonical deployment

| | |
|---|---|
| Contract | `0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622` |
| Deployment tx | `0x5b506b956b08f37cef803bf8e7b82034ef519ddde7849e164341232507121d13` |
| Status | FINALIZED, leader execution SUCCESS, AGREE x5 |
| Source commit | `3f0ffc8d9c18c63d357aabcda2ce7b8c2b6b4cd7` |
| Source sha256 | `9f80658222c138e429be091fbfde90c0c68e4fea4ded0bcac07dbb557eeaeaee` |
| Parity | byte-identical to `contracts/spec_court.py` |
| Version | 0.1.0 |

The record is [`deploy/deployment.json`](../deploy/deployment.json).

## Verification of record

`python -m pytest tests/integration -q` reads the chain and checks that the
deployed source is this repository's, that the schema is the whole surface,
that the contract holds no balance, and that every round, verdict, standing and
listing the live run recorded is still what the registry answers.
13 passed.

## How the contract reached deployment

The contract was not deployed and then repaired. It was read adversarially
before its first deployment, by fresh readers who had not written it, and
changed until a round came back with nothing to fix. Six rounds:

| Round | What it found | What changed |
|---|---|---|
| 1 | a standing could be chosen by the order of `finalize` calls; a lifetime ran from finalization; the listing could be flooded; a lookalike name made a second subject; a silent chain read as "no contract"; loose reading of the endpoint's answer; the subject was shown to the panel | one open submission per subject at a time; lifetime from the reading; listing limited to final submissions, one per submitter; subjects keyed by how they read; chain silence decides nothing under a mandatory clause; strict JSON-RPC parsing; the panel sees clauses and documents only |
| 2 | the listing could be filled without a round; a stranger's round in an outage could hold a subject; a lifetime shorter than the contest window; leader-written details stored for rounds nobody compared; short names accepted as binding | only read submissions are listed; the submitter may give up an unread submission; lifetime must exceed the contest window; undecided rounds store only what was agreed; names under eight letters refused for a mandatory binding |
| 3 | a submitter could run out the round budget to void the issuer's contest; small inaccuracies in standing, give-up reason and listing | unreadable retries are charged to the submitter; a contest unanswered at the last round stays open; a given-up submission says so; an expired entry leaves the listing first |
| 4 | a submitter with no rounds left could not answer the issuer's open contest even with the evidence back | the issuer may retry its own open contest once the submitter cannot |
| 5 | the issuer's own retries were uncounted | they count against the issuer's three |
| 6 | nothing to fix | - |

## Earlier deployments

Two, both of the same source, both kept under `deploy/diagnostics/`:

- a disposable rehearsal (`deployment_0xf5a38f83.json`): publish, thirteen
  submissions and the assessment rounds, run to confirm that validators could
  fetch the pinned evidence and reach the chain endpoint. 29 of 29 outcomes held.
- a first canonical attempt (`deployment_0x0dbccff6_interrupted.json`): the live
  run stopped part-way when the machine driving it went to sleep, and the
  one-hour assessment windows of three submissions passed before it could
  resume. Nothing in it missed; it was incomplete, so the run of record was
  made again from the start on a fresh deployment rather than patched.

## Live run of record

`scripts/live_run.py` drives the deployed contract with real transactions from
sixteen wallets and records every step in
[`deploy/live_run_transcript.json`](../deploy/live_run_transcript.json): the
transaction hash, its status, the leader's execution result, the validators'
votes, and what the registry answered afterwards. Evidence is served from this
repository at a pinned commit, by the raw host and by its CDN mirror. All of it
is synthetic and marked as test data.

| | |
|---|---|
| Contract | `0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622` |
| Evidence pinned at | commit `3f0ffc8` |
| Started / finished | 2026-10-05T03:02:18Z / 2026-10-05T05:01:10Z |
| Transactions | 72 |
| Consensus rounds | 16 |
| Outcomes checked on chain | 46 of 46 held |
| Refusals | 22 of 22 refused, each for the reason it was sent to test |
| Missed | none |

| Path | Shown by |
|---|---|
| every mandatory clause met, optional one too | SC01: `COMPLIANT` |
| compliant, then contested by the issuer and upheld | SC02 |
| a judged clause not met: royalties mentioned, never stated | SC03: `PARTIALLY_COMPLIANT` |
| no mandatory clause met | SC04: `NON_COMPLIANT` |
| evidence that addresses the adjudicator | SC05: judged clauses not met without the panel; checks still decided |
| a pinned digest the served bytes do not match | SC06: the round decides nothing; `UNVERIFIABLE` when the window passes |
| dead addresses, then a mirror added | SC07: unread, then read and `COMPLIANT` |
| first address dead, second serves the bytes | SC08: read from the mirror |
| good documentation of another contract | SC09: the binding check is not met |
| a contract that was never deployed | SC10: the chain lookup says no code |
| withdrawn before any round | SC11 |
| a picture where text was asked for | SC12: no clause that reads it is met |
| unread, and given up early by its submitter | SC13: `GIVEN_UP_BY_SUBMITTER`; nobody else could close it early |
| a revised specification, a certificate with a lifetime, a retired version | the versions phase |

## Mutation sweep

`scripts/mutation_check.py` breaks one rule of the contract at a time in a
scratch copy and runs the Direct Mode suite against it; a mutation the suite
does not notice is a rule nothing tests. The sweep of record is
[`deploy/mutation_sweep.txt`](../deploy/mutation_sweep.txt): 242 mutations, 242 killed. It ran in
several passes because one pass outlasts the time a single job may run here: a
later pass carries over the mutations an earlier pass of the same contract
killed and runs the rest. The first complete sweep left twelve survivors; ten
were rules no test exercised on their own and now have tests in
`tests/direct/test_court_rules.py`, and two were guards that repeat another
guard and were removed from the list, with the reason recorded beside it.
