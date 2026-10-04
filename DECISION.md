# Decision record - Specification Compliance Court

Written before the contract. It fixes what the contract decides, what it refuses
to decide, and why each boundary sits where it does.

## The trust question

Grant programmes, hackathons, DAOs and protocol standards all publish
requirements, and all then face the same question about every applicant:

> **Given a specification published as numbered clauses before any submission,
> and the evidence a submitter pinned for a named subject, which clauses does
> the evidence substantiate - and so does the subject comply with that version
> of the specification?**

The court judges things against specifications. It does not judge people, does
not rank submissions against each other, and has no opinion on whether a
specification is a good one.

## The delete-GenLayer test

Delete GenLayer and compliance is whatever the issuer's reviewer says after
reading the documents in private. "The documentation describes how royalties
are set and who can change them" is satisfied or not by a page of documentation.
That is a reading: deterministic code cannot make it, and one reviewer's answer
is one party's word. Several independent validators can each fetch the same
pinned document, read it against the same published clause, refuse a leader
whose reading is well-formed but wrong, and leave a typed result another
contract can rely on.

Everything code can decide stays in code: whether required fields are there,
whether the bytes match the digest, whether a contract exists at an address,
whether a document contains a passage. GenLayer handles the contextual
judgement; it does not replace a test that code can run.

## Collision audit (the owner's own portfolio)

The nearest repositories are described by what they do, not named.

| Nearest | What it decides | Why this is different |
|---|---|---|
| a capability-verification contract | whether an agent's evidence demonstrates one capability against a standard published first | one capability, one agent, one verdict; this is a registry of versioned specifications with typed clauses, any number of subjects per specification, and a standing other contracts query |
| a semantic-agreement contract | whether each requirement of a two-party agreement was satisfied, with consequences between those parties | a private agreement between two signers; here the specification is public, the issuer is not a counterparty to anything, and the result is a certificate, not a settlement |
| a grant adjudication contract | whether a grant should be awarded or a milestone paid | a funding decision with money attached; this decides compliance only, holds no funds, and a grant programme is one of its consumers |

## The rule that makes it distinct

**A specification is published once per version, as clauses, and every subject
is judged against the same clauses.** A clause is either a `CHECK` that code
decides or a `JUDGED` clause that a panel reads, and is either `MANDATORY` or
`OPTIONAL`. The verdict is derived from the clause states by a fixed rule, so
two subjects with the same clause states always get the same verdict, and a
consumer can ask one question: *does this subject hold a valid certificate for
version n of specification S?*

Revising a specification creates a new version. Certificates name the version
they were issued under and are never carried over.

## Responsibility split

**Deterministic code owns:** identity (issuer and submitter are signers); the
immutable specification versions and their hashes; which fields a submission
must carry and their types; URL admission and the specification's evidence
hosts; the sha256 pin of every document and the digest check every round; how
bytes become text; whether a contract exists at a supplied address, asked of an
RPC endpoint the specification names; every `CHECK` clause; text addressed to
the adjudicator; the verdict rule; windows from transaction time; who may act
and when; certificate validity.

**GenLayer consensus owns meaning:** whether the pinned evidence substantiates a
`JUDGED` clause.

**The model never names a verdict.** It returns, per judged clause, MET or
NOT_MET, with the passage that shows a MET. Code derives the verdict.

## The specification (immutable per version, hashed)

```json
{
  "title": "Open collection standard (test only)",
  "summary": "what the specification is for - context, never a clause",
  "fields": [
    {"id": "docs", "label": "Documentation", "type": "DOCUMENT", "required": true},
    {"id": "metadata", "label": "Sample token metadata", "type": "DOCUMENT", "required": true},
    {"id": "contract", "label": "Collection contract", "type": "ADDRESS", "required": true},
    {"id": "project", "label": "Project name", "type": "TEXT", "required": true}
  ],
  "clauses": [
    {"id": "k1", "level": "MANDATORY", "kind": "JUDGED",
     "text": "The documentation states the royalty rate and who can change it."},
    {"id": "k2", "level": "MANDATORY", "kind": "CHECK", "text": "The collection contract is deployed.",
     "check": {"type": "CODE_AT", "field": "contract", "value": "ethereum"}},
    {"id": "k3", "level": "MANDATORY", "kind": "CHECK", "text": "The metadata sample is a JSON object.",
     "check": {"type": "VALID_JSON", "field": "metadata", "value": "object"}},
    {"id": "k4", "level": "MANDATORY", "kind": "CHECK", "text": "The documentation names the contract.",
     "check": {"type": "CONTAINS_FIELD", "field": "docs", "value": "contract"}},
    {"id": "k5", "level": "OPTIONAL", "kind": "JUDGED",
     "text": "The documentation describes how holders can verify the artwork's provenance."}
  ],
  "chains": [{"id": "ethereum", "rpc_url": "https://ethereum-rpc.publicnode.com/"}],
  "evidence_domains": ["raw.githubusercontent.com", "cdn.jsdelivr.net"],
  "assess_window": 86400,
  "contest_window": 86400,
  "certificate_ttl": 0
}
```

One to eight clauses, at least one of them mandatory; one to six fields, at most
four of them documents.

| Field type | Holds | Checked at submission |
|---|---|---|
| `DOCUMENT` | a sha256 and one to three addresses that serve those bytes | digest format, URL admission, host on the specification's list |
| `ADDRESS` | a 0x address | format |
| `TEXT` | a short string | length, no hidden or control characters |

A submission that lacks a required field is refused before it is recorded.

| Check | Met when |
|---|---|
| `CONTAINS` / `NOT_CONTAINS` | the document's text has / lacks a passage, word for word |
| `RAW_CONTAINS` / `RAW_NOT_CONTAINS` | the document's source has / lacks an exact string |
| `MIN_WORDS` | the document's text has at least that many words |
| `MAX_BYTES` | the file is no larger than that |
| `VALID_JSON` | the file parses as JSON (`any`, `object` or `array`) |
| `CONTAINS_FIELD` | the document's text names the value of another field of the same submission, or its `subject` - the check that binds evidence to what it is submitted for. An address is found as itself; a name by its words, and only if it has eight letters or more, so that it could not be found in any document whatever |
| `CODE_AT` | a contract exists at the address, on a chain the specification names. A wallet that only delegates to code elsewhere is not a contract deployed there |

A check on an optional field the submission left out is not met. Two checks no
document could satisfy together are refused when the specification is
published.

**Evidence is text**, encoded as UTF-8, pinned by digest. A live page that can
change is not evidence: nobody could say later what was read.

## The verdict rule

Every clause ends MET or NOT_MET. The burden is the submitter's: what the
evidence does not show is not met.

| Verdict | When |
|---|---|
| `COMPLIANT` | every mandatory clause is met |
| `PARTIALLY_COMPLIANT` | some mandatory clause is met and some is not |
| `NON_COMPLIANT` | no mandatory clause is met |
| `UNVERIFIABLE` | the evidence could not be read when it had to be: no round could fetch it, or reach the chain, before the window closed |

Optional clauses never change the verdict; a certificate reports how many were
met.

## State machine

```text
publish_spec (issuer) ─► SPEC v1 ─revise_spec─► v2 ...   retire_version (issuer): no new submissions

submit (anyone but the issuer) ─► SUBMITTED ─assess (a consensus round)─► ASSESSED ─(contest window)─► finalize ─► FINAL
   │                                  │  └─ a round that decides nothing is recorded; the window restarts
   ├─ withdraw_submission             └─ lapse (anyone, after the assessment window) ─► FINAL, UNVERIFIABLE
   │  (submitter, before any reading)
   ├─ add_mirror (submitter): one more address for the same pinned bytes
   └─ lapse (submitter, early, once a round decided nothing) ─► FINAL, UNVERIFIABLE

ASSESSED ─contest (submitter or issuer, one read contest each; restarts the window)
```

| Situation | Rule |
|---|---|
| a document cannot be fetched | the round decides nothing and is recorded; the retries are the submitter's, whose evidence it is |
| a chain a MANDATORY clause depends on cannot be reached | the round decides nothing and is recorded; the submitter or the issuer may ask again - the endpoint is the issuer's choice, not the submitter's evidence. A silent chain under an OPTIONAL clause holds nothing up: that clause is not met |
| the model's answer cannot be used | the round decides nothing; the submitter or the issuer may ask again |
| no round reads the evidence before the assessment window ends | `UNVERIFIABLE`, and the certificate says which it was: the evidence, the chain, no usable reading, or nobody asked |
| a contest cannot reach a chain, or gets no usable answer | nothing changes and no contest is left open; the attempt is the asker's - except a submitter's retry of the issuer's open contest, which is charged to nobody |
| a contest cannot fetch the evidence | the contest stays open and the retries are the submitter's; each retry that still cannot fetch it counts against the submitter's three contest rounds - the same three its own contests use. When the submitter has none left, the issuer may ask again for its own open contest, so evidence that is back can still be read; each retry the issuer sends counts against the issuer's three. The issuer's first contest that finds the evidence dark is not counted. If nothing reads the evidence before the window ends, a favourable verdict becomes `UNVERIFIABLE`: a certificate does not survive its evidence disappearing while it is being questioned. An unfavourable verdict stands - going dark never improves one |
| the last round a submission may have leaves an issuer's contest that could not fetch the evidence unanswered | the contest stays open, with the same consequence: the issuer has no round left to ask again, so the verdict it questioned does not become final as it was |
| the evidence carries text addressed to the adjudicator | every judged clause is not met, without the panel; the phrases are published in `get_config` |

## The panel's question

For each `JUDGED` clause, in the issuer's published words: does the pinned
evidence substantiate it?

| State | Means | Must quote |
|---|---|---|
| `MET` | the evidence shows the clause is satisfied | a passage of a document that shows it |
| `NOT_MET` | it does not show that | nothing |

The panel is shown the specification's clauses and the text of the documents,
and nothing else the submitter wrote: not the subject's name, not its ADDRESS
or TEXT fields. Those are claims; a claim put in front of the reader is an
argument, not evidence. They are stored and served as claims, and code - not
the panel - checks whether a document names them.

## The derivation (code, in this order)

1. every supplied document is fetched from its addresses until one serves the pinned bytes; if none does for any document, the round is `EVIDENCE_UNAVAILABLE` and decides nothing
2. every `CODE_AT` clause asks the named RPC endpoint whether code exists at the address; if an endpoint a MANDATORY clause depends on cannot be reached, the round is `EVIDENCE_UNAVAILABLE`
3. every other `CHECK` clause is decided in code
4. a document carries text addressed to the adjudicator, or no document has any text -> every `JUDGED` clause is `NOT_MET`, without the panel
5. otherwise the panel reads the `JUDGED` clauses; an answer unusable for any one of them makes the round `PANEL_UNUSABLE`, which decides nothing
6. the verdict follows from the clause states by the rule above

## What validators compare

What each node could do with each document; for each one read, its size, the
digest of its text and its title; what each chain lookup returned; the markers;
the state of every clause; the verdict. For a round that decides nothing,
nodes agree on that and on why - which document failed and which endpoint was
silent differ between honest nodes in one outage, so in the record of a round
that could not fetch the evidence or reach a chain the status of each source
and each lookup is the leader's own account. Notes, the choice of passage, how a
fetch failed and which address answered are the leader's own account and are
listed as such in every record.

## Certificates and the registry

A final submission is a certificate. It names the specification version, the
subject, the submitter, the verdict, each clause's state, and when it stops
being valid if the specification sets a lifetime. The lifetime runs from the
round that read the evidence, not from whenever somebody finalized, and a
certificate says nothing about a time before it was final.

Standing is kept per submitter: `get_standing(spec_id, version, submitter,
subject, as_of)` answers with that submitter's latest final verdict for that
subject. Nobody else's submission can change it, so a third party cannot grief a
subject with a bad submission in its name. It answers for the latest standing,
not for history: asked about a time before that standing was final it says
`not_yet_valid` and not compliant, even if an earlier certificate was valid
then - `get_certificate` answers for one certificate at any time. `find_certificates` lists who has
submitted for a subject, for a consumer that must choose whose evidence to
trust.

A submitter may submit a subject against one specification version three
times, one at a time: while one is open the next is refused, so a subject's
submissions become final in the order they were made and the latest final one
is always the newest reading. Nobody can choose a standing by the order of
their `finalize` calls. Each certificate carries its number.

A submission no round could read says nothing about the subject. It is final
and `UNVERIFIABLE`, and it replaces no standing that rests on a reading: a
renewal that lapses - the host down, the chain silent, nobody asking - leaves
the earlier certificate where it was. Among submissions nobody read, the latest
is the standing. Once a round has been asked for and decided nothing, the
submitter may give the submission up at once, so nobody's round during an
outage can hold a subject for the length of a window; the certificate then says
`GIVEN_UP_BY_SUBMITTER`, and nothing about a window that never passed.

A renewal that was read is the standing from then on, whatever becomes of it.
If its evidence then disappears under contest, the standing is `UNVERIFIABLE`:
the submitter put its latest evidence forward, and that evidence did not stay
to be questioned. The earlier certificate is still there to be read by its id.

A subject is keyed by how its name reads: case, spacing and lookalike letters do
not make two subjects of one, and a name may not contain characters that take
no space. `find_certificates` lists final submissions that a round read, one per
submitter, at most fifty; when it is full an entry whose lifetime has run out
makes way, or else one that is not `COMPLIANT`.

## Three consumers

| Consumer | Reads |
|---|---|
| a grant programme or hackathon gating entries | `is_compliant` for the applicant's own submission, before it accepts the entry |
| a DAO or marketplace listing collections, agents or protocols that meet a standard | `find_certificates` and `get_certificate`: each clause's state and the passage it rests on |
| another contract that must act only for compliant subjects | `get_standing`, with the time it is asking about |

## Known limits

- **Evidence is what the submitter pins.** The court says whether the pinned
  documents substantiate the clauses. It does not know whether the documents are
  true, or whether they describe the subject at all, beyond what a clause checks.
  `CONTAINS_FIELD` and `CODE_AT` are the tools an issuer has to bind evidence to
  a subject; an issuer who needs more must write it as a clause.
- **A submitter who operates the host** can stop any round being recorded. The
  result is `UNVERIFIABLE`, never a better verdict.
- **A chain lookup trusts the endpoint the specification names.** An issuer
  should name an endpoint it does not control alone and that validators can
  reach. Every validator sends a request there, the address is public and
  permanent, and it may not carry a query string - a key in it would be a key
  given away. An endpoint that falls silent decides nothing; one that lies is
  believed. Only a query string is refused: a key in the path is a key given
  away just the same.
- **A document that names an address does not vouch for it.** `CONTAINS_FIELD`
  finds the address in the text; a page that lists it under "addresses that are
  not ours" names it too.
- **The marker phrases and the lookalike-letter table are tripwires**, not
  complete defences. What stands against planted instructions is that evidence
  is given to the model as data, that MET must quote a passage that is there,
  and that validators read independently.
- **The text of a document is fixed by rule, not by a browser.** Markup is
  removed for a full HTML document; text a stylesheet hides is read; text a
  stylesheet adds is not.
- **Words are counted for scripts written with spaces**, and for Chinese and
  Japanese by the character.
- **A verdict can be shopped for, within limits.** Three submissions per
  submitter, subject and version; each needs consensus, and the issuer may
  contest each one. A name that reads alike but is not folded - a capital I for
  a small l - is another subject with its own three.
- **Three submissions is also three lifetimes.** Where a specification sets a
  lifetime, one submitter can certify one subject three times under one
  version. After that it takes a new version from the issuer.
- **A lifetime is shortened by time spent under contest.** It runs from the
  reading; rounds that decide nothing restart the contest window without a new
  reading, and a certificate is valid only once somebody has called `finalize`.
  A lifetime must be longer than the contest window, and should be much longer.
- **The listing holds fifty.** Filling it for one subject costs a consensus
  round for each entry, and a full listing of unexpired `COMPLIANT` entries
  takes no more. `get_standing` for a known submitter is never affected.
- **An issuer who runs the endpoint can stall a submission** by letting the
  chain fall silent: the submission cannot be read until it answers. The
  submitter can give the submission up, and an earlier certificate is not
  touched; a lying endpoint is the stronger form of the same trust.
- **An issuer can use up a submission's assessment rounds** without running
  anything: after a round the chain or the model failed, the issuer may ask
  again, and five rounds is all a submission has. It costs the submitter one of
  its three submissions for that subject and version, and never a certificate
  it already holds.

## Deliberately left out

- **Judging people, or ranking submissions.**
- **Money.** No fee, no bond, no reward. The contract holds no funds and no
  write is payable.
- **Reading live pages.** Evidence is pinned.
- **Revoking a certificate.** A verdict is a consensus result; the issuer can
  contest it in its window and can revise or retire the specification, not
  overrule a reading.
- **A frontend.** The contract is the product.
