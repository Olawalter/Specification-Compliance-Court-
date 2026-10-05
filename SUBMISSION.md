# Submission - Specification Compliance Court

Copy-ready for the portal's Builder > Intelligent Contracts form. No addresses,
hashes or shell commands appear in the free-text fields: the contract goes only
in the evidence row the portal recognises as a GenLayer Explorer contract.

## Category

Compliance / standards verification / registry (portal: Builder > Intelligent Contracts)

## Title

Specification Compliance Court - a public registry of specifications and of what complies with them

## One-line thesis

A GenLayer Intelligent Contract where an issuer publishes a specification as clauses, anyone pins evidence for a subject, code decides every clause code can decide, independent validators read the rest, and the result is a certificate another contract can query.

## Repository

https://github.com/Olawalter/Specification-Compliance-Court-

## Canonical StudioNet address

`0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622`

## Explorer URL

https://explorer-studio.genlayer.com/address/0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622

## Deployment tx

`0x5b506b956b08f37cef803bf8e7b82034ef519ddde7849e164341232507121d13` - FINALIZED, leader execution SUCCESS

## Deployment source

commit `3f0ffc8`, `contracts/spec_court.py`, version 0.1.0; deployed source byte-identical to that commit

## Why GenLayer is required

Whether a page of documentation "states the royalty rate and who can change it" is a reading. Code cannot make it and one reviewer's answer is one party's word. Validators each fetch the pinned document, read it against the published clause with their own model, and refuse a leader whose answer the document does not support.

## Consensus mechanism

One custom leader/validator round per assessment or contest. Every validator fetches the pinned bytes itself, asks the chain itself, recomputes every code-decided clause, re-grounds every quoted passage in its own text, and compares each clause's state and the verdict with the leader's.

## Deterministic responsibilities

Identity, immutable hashed specification versions, field types, evidence hosts, sha256 pinning, how bytes become text, nine kinds of check including whether a contract exists at an address, the verdict rule, windows, certificate validity, standing and the listing.

## Failure policy

A round that cannot fetch the evidence, reach the chain a mandatory clause needs, or get a usable model answer decides nothing and is recorded. A window that passes with no reading ends unverifiable. No failure produces a better verdict than a reading would have.

## Reuse surface

A grant programme or hackathon gates entries on one boolean; a DAO or marketplace lists subjects that meet a standard and reads each clause's state; another contract asks for a submitter's standing at a given time.

## Test results

122 Direct Mode tests; 242 of 242 mutations killed; 13 integration tests reading the deployed contract; six adversarial review rounds before the first deployment, the last with nothing to fix.

## Live evidence

72 transactions on StudioNet from sixteen wallets: thirteen catalogue cases through every path, 16 consensus rounds, 46 of 46 expected outcomes, 22 of 22 refusals for their own reason, each outcome checked against on-chain state.

## Limitations

Evidence is what the submitter pins and is not checked for truth; a chain lookup trusts the endpoint the specification names; planted-instruction and lookalike-letter defences are tripwires; test network, synthetic data, no third-party audit.

## Portal description (947 characters, limit 1000)

Specification Compliance Court is a public registry that answers one question: does this subject comply with that specification? An issuer publishes a specification once per version as numbered clauses. Anyone pins evidence for a subject by digest. Clauses code can decide are decided by code: a field is present, a document contains a passage, a file is valid JSON, a contract exists at an address. Clauses that need a reading go to validators, who each fetch the pinned document, answer met or not met per clause, and must quote the passage a met rests on. The model never names a verdict: compliant, partially compliant, non-compliant or unverifiable follows from the mandatory clauses by a fixed rule. Grant programmes, hackathons, DAOs and other contracts read the certificate with one call. The contract holds no funds. Evidence that cannot be read decides nothing, and no failure improves a verdict. Tested with synthetic data on StudioNet.

## Evidence rows

| Type | Value |
|---|---|
| GenLayer Explorer contract | https://explorer-studio.genlayer.com/address/0xaFCed3F4bcbC85791cd0a0890bfbFa6Fd419f622 |
| GitHub repository | https://github.com/Olawalter/Specification-Compliance-Court- |

## Reviewer fast path

Read `DECISION.md`, then `docs/CONSENSUS.md`, then `deploy/live_run_transcript.json`; run `python -m pytest tests/direct -q` and `python -m pytest tests/integration -q`.
