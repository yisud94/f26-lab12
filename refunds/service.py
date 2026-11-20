"""The surface the CampusReserve platform calls.

One cancellation in, one refund statement out. The service checks that the
request and the booking agree, asks the policy what comes back, and assembles
the statement the platform files against the cancellation.
"""

from __future__ import annotations

from refunds.models import (
    BookingRecord,
    CancellationRequest,
    RefundStatement,
    format_cents,
)
from refunds.policy import refund_cents, tier_for


class RefundRequestError(ValueError):
    """The request and the booking do not describe the same reservation."""


def validate_request(booking: BookingRecord, request: CancellationRequest) -> None:
    """Reject anything the policy has no honest answer for."""
    if request.booking_id != booking.booking_id:
        raise RefundRequestError(
            f"cancellation names booking {request.booking_id}, "
            f"record is {booking.booking_id}"
        )
    if not booking.interval.is_well_formed():
        raise RefundRequestError(f"booking {booking.booking_id} has an unusable interval")
    if request.requested_at.tzinfo is None:
        raise RefundRequestError("cancellation timestamps must carry a timezone")
    if booking.price_as_booked_cents < 0:
        raise RefundRequestError(f"booking {booking.booking_id} has a negative price as booked")
    if request.requested_at < booking.booked_at:
        raise RefundRequestError(
            f"cancellation for {booking.booking_id} predates the booking itself"
        )
    if not request.requested_by:
        raise RefundRequestError(f"cancellation for {booking.booking_id} names no requester")


def build_statement(
    booking: BookingRecord,
    refund: int,
    tier_name: str,
    adjustments: list[str] | None = None,
) -> RefundStatement:
    """Assemble the statement the platform files against the cancellation."""
    adjustments = [] if adjustments is None else list(adjustments)
    adjustments.append(f"settled under the {tier_name} tier")
    withheld = booking.price_as_booked_cents - refund
    if withheld > 0:
        adjustments.append(
            f"withheld {format_cents(withheld)} of "
            f"{format_cents(booking.price_as_booked_cents)}"
        )
    return RefundStatement(
        booking_id=booking.booking_id,
        price_as_booked_cents=booking.price_as_booked_cents,
        refund_cents=refund,
        tier_name=tier_name,
        adjustments=tuple(adjustments),
    )


def decide_refund(booking: BookingRecord, request: CancellationRequest) -> RefundStatement:
    """Price one cancellation."""
    validate_request(booking, request)
    tier = tier_for(booking, request)
    amount = refund_cents(booking, request)
    notes: list[str] = [f"room {booking.room.label}, {booking.department}"]
    if request.reason:
        notes.append(f"reason on file: {request.reason}")
    return build_statement(booking, amount, tier.name, adjustments=notes)


def index_bookings(bookings):
    """Bookings keyed by id, for matching a batch of cancellations."""
    return {booking.booking_id: booking for booking in bookings}


def decide_batch(
    bookings: list[BookingRecord],
    requests: list[CancellationRequest],
) -> list[RefundStatement]:
    """Price a batch of cancellations against the bookings they name."""
    index = index_bookings(bookings)
    statements: list[RefundStatement] = []
    for request in requests:
        booking = index.get(request.booking_id)
        if booking is None:
            raise RefundRequestError(f"no booking on file for {request.booking_id}")
        statements.append(decide_refund(booking, request))
    return statements


def total_refunded_cents(statements: list[RefundStatement]) -> int:
    """What a batch of statements costs the campus in total."""
    return sum(statement.refund_cents for statement in statements)


def render_statement(statement: RefundStatement) -> str:
    """The statement as a block of text, for logs and support tickets."""
    lines = [
        f"Booking {statement.booking_id}",
        f"  price as booked: {format_cents(statement.price_as_booked_cents)}",
        f"  refund: {format_cents(statement.refund_cents)}",
        f"  withheld: {format_cents(statement.withheld_cents)}",
        f"  tier: {statement.tier_name}",
    ]
    for note in statement.adjustments:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def activity_line(statement: RefundStatement) -> str:
    """One line for the platform's activity feed."""
    return (
        f"{statement.booking_id}: {format_cents(statement.refund_cents)} back of "
        f"{format_cents(statement.price_as_booked_cents)} ({statement.tier_name})"
    )


def render_batch(statements: list[RefundStatement]) -> str:
    """A batch of statements plus what the batch costs in total."""
    blocks = [render_statement(statement) for statement in statements]
    blocks.append(f"batch total: {format_cents(total_refunded_cents(statements))}")
    return "\n\n".join(blocks)
