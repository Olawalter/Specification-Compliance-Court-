# Security, privacy and what a certificate means

## What this contract is not

It is not an audit, a safety rating, a legal opinion or an endorsement. It
holds no funds. It does not verify that a document is true, that a subject
exists, or that a submitter has any right to speak for the subject. It decides
one thing: whether the evidence pinned to a submission substantiates the
clauses of one version of one specification.

## What a verdict means - and does not

`COMPLIANT` means every mandatory clause of that version was MET on the pinned
evidence, by code for `CHECK` clauses and by validator consensus for `JUDGED`
ones. It does not mean the subject is good, safe or honest. `UNVERIFIABLE`
means nothing could be read in time; it is not a finding against the subject.

A consumer should always name the specification version it relies on, pass the
time it is asking about, and decide for itself whose submission it trusts:
standing is kept per submitter.

## Assets

| Asset | Protected by |
|---|---|
| a specification version | stored verbatim and hashed at publication; no method rewrites it |
| a submission's evidence | pinned by sha256; every round re-checks the bytes |
| a verdict | derived in code from compared clause states; changed only by a later round that read the evidence |
| a submitter's standing | keyed by submitter; nobody else's submission touches it, and a submission no round read replaces nothing |
| each party's contest | counted separately; neither party can spend the other's |

## Actors

| Actor | Can | Cannot |
|---|---|---|
| issuer | publish, revise and retire its specification; contest an assessment once; retry a round its endpoint or the model failed | submit under its own specification; change a published version; overrule or revoke a verdict |
| submitter | submit, add addresses for the same bytes, withdraw before any round, contest once, give up an unread submission | change what was pinned; have two open submissions for one subject and version; submit a subject more than three times per version |
| anyone | ask for the first round; finalize after the window; lapse after the window | retry a round on evidence that was unreadable; contest; close someone's submission early |
| leader | propose a round's result | get it stored without validators reproducing it |
| validator | refuse a result | change one |

## Trust assumptions

- A majority of validators run the round honestly.
- The evidence hosts the specification allows serve what was pinned, or serve
  nothing. A host cannot serve different bytes unnoticed: the digest is checked.
- The chain endpoint a specification names answers truthfully. This is the
  issuer's choice and the issuer's risk to state: an endpoint that lies is
  believed, and one the issuer controls can stall a submission.
- Transaction time is the network's.

## Input attacks

| Attack | Defence |
|---|---|
| instructions to the model planted in a document | documents are given as data; the published marker phrases make every judged clause NOT_MET without the model; MET must quote a grounded passage; validators read independently |
| instructions planted in the subject or a text field | the panel is not shown them; they are refused at submission if they carry a marker phrase |
| hidden or zero-width characters, lookalike letters | removed or folded before text is compared; a subject may not contain characters that take no space |
| markup that splits or joins words | only block elements separate text; inline tags and comments do not |
| a quote stitched from fragments | refused |
| a second subject that reads like the first | subjects are keyed by how the name reads |
| flooding a subject's listing | only submissions a consensus round read are listed, one per submitter, at most fifty |
| holding a subject by starting a round during an outage | the submitter may give the submission up at once and submit again |
| an oversized or malformed chain answer | size-capped; only a strict JSON-RPC answer counts |
| an RPC address carrying a key | a query string is refused at publication |
| a document address outside the allowed hosts, or not plain https | refused at submission |

## Privacy and data minimisation

Everything written to the contract is public and permanent: the specification,
the subject's name, every field value and every address. Do not submit personal
data, credentials or anything confidential, and do not pin a document that
contains them. The contract stores the digests, sizes and titles of documents
and the short passages quoted for a MET; it does not store the documents.

## Fail-closed policy

When the contract cannot read, it does not guess. Unreadable evidence, a silent
chain under a mandatory clause and an unusable model answer each produce a
round that changes nothing. A window that passes with no reading ends in
`UNVERIFIABLE`. A favourable verdict whose evidence goes missing while it is
contested becomes `UNVERIFIABLE`. No failure path produces a better verdict
than a successful reading would have.

## Limitations

- Evidence is what the submitter pins. A document that names an address does
  not vouch for it.
- The marker phrases and the lookalike table are tripwires. A lookalike that is
  not in the table makes a different subject, with its own three submissions.
- A verdict can be asked for three times per submitter, subject and version,
  and where a lifetime is set that is three lifetimes.
- A certificate's lifetime runs from the reading, so time spent under contest
  shortens it.
- A submitter who runs the host, or an issuer who runs the endpoint, can keep a
  submission from being read. Neither can improve a verdict that way.
- Text is derived by rule, not by a browser: text a stylesheet hides is read,
  and text a stylesheet adds is not.
- StudioNet is a development network. The deployment demonstrates the
  mechanism with synthetic data.
