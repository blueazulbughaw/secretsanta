import random
from datetime import datetime

from ..extensions import db
from ..models import Event, EventParticipant, FamilyMember, Assignment
from .codenames import generate_codenames
from .notification_service import notify


class MatchingError(Exception):
    """Human-readable problem the admin can fix."""


def validate_event(event: Event):
    """Returns list of (user_id, household_id) or raises MatchingError
    with plain-language messages."""
    if event.status not in ("open", "draft"):
        raise MatchingError("Names have already been drawn for this event.")

    parts = (EventParticipant.query
             .filter_by(event_id=event.id, is_participating=True).all())
    if len(parts) < 3:
        raise MatchingError("You need at least 3 people to draw names.")

    memberships = {
        m.user_id: m for m in FamilyMember.query.filter_by(
            family_id=event.family_id).all()
    }

    participants = []
    problems = []
    for p in parts:
        m = memberships.get(p.user_id)
        if m is None:
            problems.append(f"{p.user.display_name or p.user.full_name} is not in this family anymore.")
            continue
        if m.household_id is None:
            problems.append(f"Please put {p.user.display_name or p.user.full_name} in a household first.")
            continue
        participants.append((p.user_id, m.household_id))
    if problems:
        raise MatchingError(" ".join(problems))

    if not event.allow_same_household:
        counts = {}
        for _, h in participants:
            counts[h] = counts.get(h, 0) + 1
        n = len(participants)
        biggest = max(counts.values())
        if biggest > n // 2:
            raise MatchingError(
                "One household has more than half of the people, so a fair draw "
                "is not possible. Add more people, split the household, or allow "
                "matches within the same household.")
    return participants


def solve(participants, allow_same_household=False, rng=None):
    """Constrained derangement via randomized block-shift.

    participants: list of (user_id, household_id).
    Returns dict giver_id -> receiver_id or raises MatchingError.

    Method: shuffle members within each household, place the LARGEST
    household first, shuffle the remaining households, lay everyone out
    in one line, then each person gives to the person `m` seats ahead
    (wrapping around), where m = size of the largest household.

    Why it's always valid when max household <= n/2:
    - No self-match: the shift m >= 1.
    - No same-household match: households sit in contiguous blocks, and
      every block has size <= m, so shifting by m always lands outside
      your own block (the wraparound lands inside the first/largest
      block, which the tail positions can never belong to when m <= n/2).
    Runs in O(n) — no backtracking, no pathological cases.
    """
    rng = rng or random
    n = len(participants)
    if n < 3:
        raise MatchingError("You need at least 3 people to draw names.")

    if allow_same_household:
        order = [p[0] for p in participants]
        rng.shuffle(order)
        return {order[i]: order[(i + 1) % n] for i in range(n)}

    groups = {}
    for uid, hh in participants:
        groups.setdefault(hh, []).append(uid)
    for members in groups.values():
        rng.shuffle(members)

    blocks = sorted(groups.values(), key=len, reverse=True)
    m = len(blocks[0])
    if m > n // 2:
        raise MatchingError(
            "No valid way to draw names with the current households.")

    rest = blocks[1:]
    rng.shuffle(rest)
    order = blocks[0] + [uid for block in rest for uid in block]
    return {order[i]: order[(i + m) % n] for i in range(n)}


def generate_assignments(event: Event):
    """Validate, solve, persist in one transaction, notify. Idempotent-safe:
    DB unique constraints reject double inserts."""
    participants = validate_event(event)
    matches = solve(participants, event.allow_same_household)

    try:
        for giver, receiver in matches.items():
            db.session.add(Assignment(event_id=event.id,
                                      giver_id=giver, receiver_id=receiver))
        if event.use_codenames:
            parts = EventParticipant.query.filter_by(
                event_id=event.id, is_participating=True).all()
            names = generate_codenames(len(parts))
            for p, name in zip(parts, names):
                p.codename = name
        event.status = "matched"
        event.matched_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    for giver in matches:
        notify(giver, "assignment", "Names have been drawn! 🎁",
               f"Tap to see who you're giving a gift to for {event.name}.",
               link_path=f"/events/{event.id}/my-person")
    return len(matches)
