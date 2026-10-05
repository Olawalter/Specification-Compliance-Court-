# Integration

For a consumer that wants to rely on a certificate, an issuer that wants to
publish a specification, and a submitter.

## The consumer's interface

```python
import genlayer as gl

@gl.contract_interface
class SpecCourt:
    class View:
        def is_compliant(self, spec_id: str, version: int, submitter: str,
                         subject: str, as_of: str) -> dict: ...
        def get_standing(self, spec_id: str, version: int, submitter: str,
                         subject: str, as_of: str) -> dict: ...
        def get_certificate(self, submission_id: str, as_of: str) -> dict: ...
        def find_certificates(self, spec_id: str, version: int, subject: str) -> dict: ...
```

`as_of` is an ISO-8601 UTC time such as `2026-10-04T12:00:00Z`. A view has no
clock, so the caller says which moment it is asking about; a contract passes
its own transaction time.

## What each view answers

| View | Answers |
|---|---|
| `is_compliant` | one boolean, `compliant`: this submitter's standing for this subject under this version is `COMPLIANT`, final, already valid and not expired at `as_of` |
| `get_standing` | the same standing in full: verdict, clause states, `valid_until`, how many times the subject was submitted |
| `get_certificate` | one submission: status, verdict, each clause's state, `final_by`, `read_at`, `valid_until`, `expired`, `not_yet_valid`, `spec_retired` |
| `find_certificates` | which submitters hold a final, read submission for a subject under a version - at most fifty, one per submitter |
| `get_resolution` | one round's record: what was read, each chain answer, each finding with its quoted passages, the verdict, whether it was applied |
| `get_history` | the rounds of a submission, in order |
| `get_actions` | what may happen to a submission next at `as_of`, and who may do it |
| `get_spec` / `get_spec_versions` | a specification version verbatim with its hash; the versions of a specification |
| `get_submission` | the pinned documents, the claimed values, the window, the state of any open round or contest |
| `list_specs` / `list_submissions` | ids, paged by `offset` and `limit` (at most fifty) |
| `get_stats` / `get_config` | counts; every vocabulary, limit and marker phrase the contract uses |

## Reading a certificate correctly

- **Name the version.** A certificate under version 1 says nothing about
  version 2. `is_latest` and `spec_retired` tell you whether the issuer has
  moved on.
- **Name the submitter.** Standing is per submitter. Anyone may submit evidence
  about any subject, so decide whose submission you accept - usually the wallet
  that is applying to you - and use `find_certificates` only to discover
  candidates.
- **Check `compliant`, not `verdict`.** `compliant` is false for a verdict that
  is not final, has expired, or is asked about before it was final.
- **`UNVERIFIABLE` is not a finding.** `final_by` says why nothing was read.
- **Field values are claims.** `values_are_claims` is always true: the contract
  checks a value only where a clause says so.
- **Subjects are matched by how the name reads**: case, spacing and listed
  lookalike letters do not make a different subject.

## Following a submission

Poll `get_actions(submission_id, now)`. `may_assess` with `assess_by` says who
may ask for a round; `open_round` says what the last round could not do;
`may_contest` says which party may still contest; `may_finalize`, `may_lapse`
and `may_give_up` say how it can end. Each round appears in `get_history`.

## Writing, for an issuer

`publish_spec(spec_json)` returns the specification id; `revise_spec` returns
the new version; `retire_version` closes one to new submissions.
[DECISION.md](../DECISION.md) has a complete example. In short:

- one to eight clauses, at least one `MANDATORY`; one to six fields, at most
  four documents;
- `evidence_domains` lists the hosts documents may be served from, and should be
  hosts that serve immutable, pinned content;
- `chains` names an RPC endpoint per chain a `CODE_AT` clause uses; it may not
  carry a query string and should be one you do not control alone;
- `assess_window` is at least an hour and `contest_window` at least fifteen
  minutes; `certificate_ttl` is 0 for no expiry, or longer than the contest
  window.

## Writing clauses that hold

- Put everything code can decide in a `CHECK`. It is cheaper, exact, and cannot
  be argued with.
- Write a `JUDGED` clause as one statement the evidence either shows or does
  not: "the documentation states the fee and who can change it", not "the
  documentation is good".
- Bind the evidence to the subject. Without a `CONTAINS_FIELD` or `CODE_AT`
  clause, a submitter can pin someone else's good documents.
- Make only what must hold `MANDATORY`. Optional clauses are reported and never
  change the verdict.

## Writing, for a submitter

`submit(spec_id, version, submission_json)` with

```json
{"subject": "the thing being certified",
 "fields": {"docs": {"sha256": "<64 hex>", "urls": ["https://..."]},
            "contract": "0x...", "project": "a short name"}}
```

Pin the bytes first, then submit their digest. Serve them from a host that
will still serve the same bytes for the length of the windows; `add_mirror`
adds another address for the same bytes if one stops. One submission per
subject and version may be open at a time, and three in all.
