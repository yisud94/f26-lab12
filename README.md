# campusreserve-refunds

Your team owns this repository. It is the refund decision service for
CampusReserve (the room booking platform from Labs 8 and 9).

The Platform team owns the booking core. When a cancellation comes in and
someone has to decide how much money goes back, the platform calls this
service, hands over the booking record and the cancellation request, and files
whatever statement comes back.

## Pricing

The platform's `billing` module prices bookings and owns invoices. It
snapshots the price when the reservation is confirmed. That snapshot (the price as booked) arrives on every
request as a whole number of cents. This service uses it as given, without
recomputing it.

## Platform conventions

- Instants are timezone-aware UTC.
- Intervals are half-open, `[start, end)`. A booking that ends at 16:00 and one
  that starts at 16:00 sit back to back.
- Durations are whole minutes.
- Money is whole cents. Percentages round down.

## The refund table

How much of the price as booked comes back depends on how long before the
booking start the cancellation is made.

| Cancelled | Tier | Comes back |
|---|---|---|
| 7 days ahead or more | full | 100% |
| 2 days ahead or more | standard | 75% |
| 1 day ahead or more | reduced | 50% |
| 2 hours ahead or more | minimal | 25% |
| anything later | none | nothing |

Two rules override the table. A short list of reasons the campus absorbs
in full (a closed room, a building emergency, a weather closure, an instructor
absence) returns the whole price as booked whatever the lead time. A payout
under one dollar costs more to move than it returns, so it is not issued.

## Code map

- `refunds/models.py`: the data the platform sends. `Room`, `Organizer`,
  `TimeInterval`, `BookingRecord`, `CancellationRequest`, and the
  `RefundStatement` that goes back.
- `refunds/policy.py`: the tier table and the rules above.
- `refunds/service.py`: the functions the platform calls. They validate the
  request against the booking, ask the policy what comes back, and assemble
  the statement.
- `tests/`: the test suite, which passes as shipped.
- `requirements.txt`: the service's runtime dependencies.

The service is annotated. A few helpers are not, which is ordinary for a
codebase that picked up type annotations after it was already running.

## Build and test

See `SETUP.md` for the toolchain and the first run. The short version, from
this directory with the virtual environment active:

```
pytest
```

The suite passes as shipped. The Lab 12 handout tells you when to use the
other three tools that `requirements-dev.txt` installs.

See the Lab 12 handout on the course page for the milestones you show a TA.

## Lab 12 write-up and AI use

The CI gate findings are in [FINDINGS.md](FINDINGS.md).

Tools and models used:

- **Claude Code** (VS Code extension), running the **Claude Opus 5.5** model
  (`claude-opus-5-5`). It wrote the CI workflow, fixed the ruff and mypy findings,
  decided how to handle the audit finding, reviewed `changes/bad-change.patch`, and drafted
  `FINDINGS.md`.
- **GitHub Actions**, which runs the pipeline in `.github/workflows/ci.yml`.
- **pytest, ruff, mypy, and pip-audit**, the four checks in that pipeline, at the versions
  pinned in `requirements-dev.txt`.
