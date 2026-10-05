# Consensus

How one round is run, what validators compare, and what a dishonest leader
cannot do. The code is `_node_round`, `_parse_payload`, `_evidence_difference`,
`_derive` and `_validator_decision` in `contracts/spec_court.py`.

## The exact nondeterministic calls

A round happens inside `assess` and `contest`, and nowhere else. Each is one
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` call. Inside it a node makes:

| Call | For | How often |
|---|---|---|
| `gl.nondet.web.get(url)` | each pinned document, trying its addresses in order until one serves the pinned bytes | at most three addresses for each of at most four documents |
| `gl.nondet.web.post(rpc_url, ...)` with `eth_getCode` | each `CODE_AT` clause, at the endpoint the specification names for that chain | once per distinct chain and address; not at all if a document was unreadable |
| `gl.nondet.exec_prompt(..., response_format="json")` | the `JUDGED` clauses, all in one prompt | once, and only if code has not already decided them |

Every other method is deterministic, including every view.

## What every node does

1. Fetches every document and checks the sha256 of the bytes against the pin.
   A document that no address serves, or whose bytes differ, makes the round
   `EVIDENCE_UNAVAILABLE`.
2. Turns the bytes into text by a fixed rule (UTF-8; for an HTML document the
   markup is removed, block elements leave a gap, inline ones do not).
3. Asks each named chain whether code exists at each supplied address. Only a
   well-formed JSON-RPC answer counts. An endpoint that gives none is
   `UNREACHABLE`: under a mandatory clause the round decides nothing, under an
   optional clause that clause is not met.
4. Decides every `CHECK` clause in code.
5. Scans the text for the published marker phrases. If a document addresses
   the adjudicator, or no document has any text, every `JUDGED` clause is
   NOT_MET by code and the model is not called.
6. Otherwise shows the model the clauses and the document text - not the
   subject's name and not the submission's ADDRESS or TEXT values - and asks,
   for each judged clause, MET or NOT_MET, with a quoted passage for MET.
7. Grounds every quote: it must be a contiguous passage of the text this node
   showed, found by its words. A MET with no grounded quote makes the answer
   unusable, and an unusable answer for any clause makes the round
   `PANEL_UNUSABLE`.
8. Derives the verdict from the clause states.

## What the leader does

Runs the steps above and returns the payload: per document what it could do
with it and what it read, each chain answer, the markers found, and one finding
per clause.

## What the validator does

Runs the same steps itself - its own fetches, its own chain lookups, its own
model call - and then, in this order:

1. **Gates the leader's payload against its own documents.** The payload must
   have exactly the expected shape; every `CHECK` finding is recomputed from the
   validator's documents and must equal the leader's; every quote the leader
   offers must be found in the text the validator read; a judged clause that
   code decided must say so.
2. **Compares the evidence.** The reason a round was or was not read; the
   markers; each chain answer; for each document whether it was readable, its
   size, the digest of its bytes, the digest of its text, its title.
3. **Compares the consequence.** The state of every clause and the verdict.

Any failure is a disagreement and prints its reason.

## What must match, what may differ

| Must match | May differ |
|---|---|
| whether each document was readable | which address served it |
| size, byte digest, text digest and title of each document read | the HTTP status and content type |
| each chain lookup's answer | how an unfetched document failed |
| the marker phrases found | the wording of a finding's note |
| MET or NOT_MET for every clause | which passage was quoted for a MET (each must be grounded) |
| the verdict | |
| for a round that decides nothing: that it does, and why | which document or endpoint failed |

What may differ is listed in every stored record under `leader_chosen`, so a
reader knows which fields are one node's account. A round that decides nothing
stores only the status of each source and no markers.

## Decision-critical fields

The clause states. The verdict is a function of the states of the mandatory
clauses and of nothing else, and every clause's state is compared. There are at
most eight clauses and two states, so there is no tolerance band to tune.

## Forged-leader defence

| A leader that | Is refused because |
|---|---|
| reports MET for a clause the document does not support | the validator's own reading says NOT_MET |
| quotes a passage that is not in the document | the gate cannot ground the quote in the validator's text |
| joins distant fragments into one quote | a quote with an ellipsis is refused, and a quote must be contiguous |
| reports a `CHECK` clause as met when it is not | the gate recomputes every check |
| says a contract exists where none does | the validator's own lookup differs |
| says the evidence was unreadable when it was not | the reason differs |
| claims the model decided what code decided, or the reverse | the gate requires each finding to name who decided it |
| returns a payload for another submission, round or specification | the submission id, round number, specification hash and commitment are part of the payload and are checked |
| fails with a made-up error | an error is ratified only by the same deterministic error, or a transient one by a transient one |

## Failure semantics

A round that decides nothing is still a transaction that reaches consensus: the
nodes agree that nothing could be decided and why. It is recorded with
`applied` false, no verdict changes, and the submission's window starts again
while a round is left. Who may ask again depends on what failed: unreadable
evidence is the submitter's to retry; a silent chain or an unusable model
answer may be retried by the submitter or the issuer.

If consensus itself is not reached, the transaction does not execute and
nothing is recorded; the call can be sent again.

## Why consensus is load-bearing

Remove the validators and every protection in the table above goes with them:
the leader's reading would be the verdict. Remove the model and no `JUDGED`
clause can be decided at all. The deterministic parts would still run, and they
are the parts that never needed consensus.

## Live findings

The run of record made 16 consensus rounds. Every one finalized with the
leader's result accepted; no validator disagreed in this run, so the forged-leader
paths are shown by the Direct Mode suite (which replays a validator against
forged payloads) and not by the live run. Two things the live network did show:

- A round that could not read the evidence reaches consensus like any other.
  Three rounds ended `EVIDENCE_UNAVAILABLE`; each was recorded with `applied`
  false and changed no verdict.
- Validators reached the public chain endpoint and both evidence hosts from
  inside a round: the `CODE_AT` clause was decided both ways (code present, no
  code), and one submission was read from its second address after the first
  served nothing.
