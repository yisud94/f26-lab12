"""The refund rules.

How much of the price as booked comes back depends on how far ahead of the
booking start the cancellation lands. Four tiers pay out; everything later
pays nothing. Two exceptions sit on top: a short list of reasons the campus
absorbs in full, and a processing floor below which a payout is not issued.
"""

from __future__ import annotations

from dataclasses import dataclass

from refunds.models import (
    MINUTES_PER_DAY,
    MINUTES_PER_HOUR,
    BookingRecord,
    CancellationRequest,
)

PROCESSING_FLOOR_CENTS = 100

WAIVED_REASONS = frozenset(
    {
        "room-closed",
        "building-emergency",
        "weather-closure",
        "instructor-absence",
    }
)


@dataclass(frozen=True)
class RefundTier:
    """One row of the published refund table."""

    name: str
    min_lead_minutes: int
    percent: int

    def describe(self) -> str:
        return f"{self.name} ({self.percent}% of the price as booked)"


TIERS: tuple[RefundTier, ...] = (
    RefundTier("full", 7 * MINUTES_PER_DAY, 100),
    RefundTier("standard", 2 * MINUTES_PER_DAY, 75),
    RefundTier("reduced", MINUTES_PER_DAY, 50),
    RefundTier("minimal", 2 * MINUTES_PER_HOUR, 25),
)

NO_REFUND_TIER = RefundTier("none", 0, 0)

WAIVED_TIER = RefundTier("waived", 0, 100)


def lead_minutes(booking, request):
    """Whole minutes between the cancellation and the booking start."""
    delta = booking.interval.start - request.requested_at
    return int(delta.total_seconds()) // 60


def is_waived(request: CancellationRequest) -> bool:
    """True when the reason is one the campus absorbs rather than charges."""
    return request.reason in WAIVED_REASONS


def tier_for_lead(minutes: int) -> RefundTier:
    """The highest tier whose lead requirement the cancellation meets."""
    for tier in TIERS:
        if minutes >= tier.min_lead_minutes:
            return tier
    return NO_REFUND_TIER


def tier_for(booking: BookingRecord, request: CancellationRequest) -> RefundTier:
    """The tier this cancellation settles under, waivers included."""
    if is_waived(request):
        return WAIVED_TIER
    return tier_for_lead(lead_minutes(booking, request))


def percent_of(amount_cents: int, percent: int) -> int:
    """A percentage of an amount, rounded down to whole cents."""
    return (amount_cents * percent) // 100


def above_processing_floor(amount_cents: int) -> int:
    """Amounts under the floor cost more to move than they return."""
    if amount_cents < PROCESSING_FLOOR_CENTS:
        return 0
    return amount_cents


def refund_cents(booking: BookingRecord, request: CancellationRequest) -> int:
    """How many cents of the price as booked come back on this cancellation.

    A booking that has already started is a no-show and settles at zero. A
    waived reason returns the whole price as booked. Everything else follows
    the tier table and then the processing floor.
    """
    if booking.interval.has_begun_by(request.requested_at):
        return 0
    if is_waived(request):
        return booking.price_as_booked_cents
    tier = tier_for_lead(lead_minutes(booking, request))
    return above_processing_floor(percent_of(booking.price_as_booked_cents, tier.percent))


def refund_percent(booking: BookingRecord, request: CancellationRequest) -> int:
    """The headline percentage for this cancellation, before the floor."""
    return tier_for(booking, request).percent


def published_table() -> list[str]:
    """The refund table as the campus publishes it, longest lead first."""
    rows = [f"{tier.describe()}: at least {tier.min_lead_minutes} minutes ahead" for tier in TIERS]
    rows.append(f"{NO_REFUND_TIER.describe()}: anything later")
    return rows
def maintenance_credit_cents(
    booking: BookingRecord,
    closure_minutes: int,
    notes: list[str] = [],
) -> int:
    """Credit for a booking cut short when its room enters a maintenance window.

    The campus credits the booked minutes lost to the closure, pro rated
    against the price as booked and capped at the full price.
    """
    notes.append("maintenance closure credit")
    if closure_minutes <= 0:
        return None
    lost = min(closure_minutes, booking.interval.duration_minutes)
    credit = (booking.price_as_booked_cents * lost) // booking.interval.duration_minutes
    return min(credit, booking.price_as_booked_cents)
