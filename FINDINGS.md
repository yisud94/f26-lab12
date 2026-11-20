# Lab 12 findings: CI gate

## The gate

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every push and pull request.
Each check runs as its own job, so one failure does not hide the others:

| Job | Command |
|---|---|
| test | `pytest` |
| lint | `ruff check .` |
| typecheck | `mypy` |
| audit | `pip-audit -r requirements.txt` |

## Runs

| Commit | What it was | test | lint | typecheck | audit | Run |
|---|---|---|---|---|---|---|
| `c2f8e97` | Gate added, code untouched | ✅ | ❌ | ❌ | ❌ | [44763782359](https://github.com/yisud94/f26-lab12/actions/runs/44763782359) |
| `dc09d2e` | Findings fixed | ✅ | ✅ | ✅ | ✅ | [44764201495](https://github.com/yisud94/f26-lab12/actions/runs/44764201495) |
| `99d4469` | `changes/bad-change.patch` applied (branch `maintenance-credits`) | ✅ | ❌ | ❌ | ✅ | [44765020560](https://github.com/yisud94/f26-lab12/actions/runs/44765020560) |

The first run is red while the tests pass on the same commit.

## What ruff caught

`refunds/service.py:48`, in `build_statement`:

```python
    adjustments: list[str] = [],
```

**Problem (B006, mutable default argument).** Python creates the default `[]` once, when the
function is defined. The function appends to it, so every call that leaves out `adjustments`
adds to one shared list, and later statements carry notes from earlier ones.

**Why the tests missed it.** Both tests pass the argument explicitly (`adjustments=[]` and
`adjustments=["batch 2026-03"]`), and so does `decide_refund`, the only caller. No test uses
the default, and the bug needs two or more calls that do.

**Fix.** The default is now `None`, and the function copies whatever list it is given.

## What mypy caught

`refunds/policy.py:102`, in `refund_cents`:

```python
        return None
```

**Problem (return-value).** The function is declared to return `int`, and its own docstring
says a booking that has already started "settles at zero". Returning `None` puts
`refund_cents=None` into the `RefundStatement`, so later arithmetic on it would crash, such as
the withheld amount in `build_statement` or a batch total.

**Why the tests missed it.** No test cancels a booking after it has started. The policy tests
all cancel before the start. The only test of `has_begun_by` checks the interval method
directly in `test_models.py` and never goes through `refund_cents`.

**Fix.** The branch now returns `0`.

## The audit finding

pip-audit flagged `babel==2.9.0` in `requirements.txt`: PYSEC-2021-421, fixed in 2.9.1.

**Decision: remove the package.** Nothing in `refunds/` or `tests/` imports babel, so the
service does not use it.

- Upgrading would keep a package nobody needs.
- Accepting it with `--ignore-vuln` is for a package you need whose vulnerability cannot be
  reached. Here it was cheaper and safer to stop shipping the package.

`requirements.txt` now holds only a comment, the audit job passes, and `ci.yml` has no
ignore entry.

## The proposed change (`changes/bad-change.patch`)

All 18 tests pass with the patch applied, but the gate failed it:

- **lint:** `notes: list[str] = []` is the same mutable default bug as above.
- **typecheck:** it returns `None` from a function declared to return `int` when
  `closure_minutes <= 0`.

Review found problems the gate does not catch:

- `notes` is filled in but never returned or read.
- There are no tests for the new function.
- It divides by `duration_minutes`, which is safe only because `validate_request` rejects
  bad intervals, and this function never goes through `validate_request`.

## Limits of the gate

- **A bad change it would still let through:** a change to the refund rules that is
  well-typed, lint-clean and not covered by a test. For example, the standard tier moves from
  2 days to 3, or a percentage rounds up instead of down. ruff and mypy check how the code is
  written, not whether the refund amounts are correct.
- **A check I would not let block a merge: `pip-audit`.** Its result can change with no change
  to our code. A newly published vulnerability report against a pinned dependency would turn
  every open PR red, including ones that only fix a typo. Better to run it on a schedule and on
  PRs that change `requirements.txt`, and have it open an issue. ruff, mypy and pytest should
  block merges, because they only fail on what the change itself introduces.
