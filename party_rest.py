"""Shared-rest transaction core. NOT an installed Skyrim integration.

The adapter must obtain party membership, leadership and rest completion from
verified game/network APIs. Client names or claimed roles are not authority.
"""
from dataclasses import dataclass, field
from math import isfinite
from typing import FrozenSet, Optional, Tuple


class RestError(ValueError):
    pass


@dataclass(frozen=True)
class Party:
    party_id: int
    revision: int
    leader: int
    members: FrozenSet[int]


@dataclass(frozen=True)
class Benefit:
    player: int
    hours: float


@dataclass(frozen=True)
class Completion:
    session: int
    benefits: Tuple[Benefit, ...]
    advance_hours: float


@dataclass
class Session:
    number: int
    party: Party
    hours: float
    deadline: float
    skip_requested: bool
    safe: set = field(default_factory=set)
    consent: set = field(default_factory=set)


class PartyRest:
    """One active transaction per party; completed sessions cannot be replayed.

    Wall-clock skipping requires unanimous consent from ALL connected players:
    the server calendar is global, even when there are several parties.
    Benefits go only to the unchanged initiating party.
    """
    def __init__(self):
        self._next = 1
        self._active = {}

    @staticmethod
    def _validate_party(party):
        if not party.members or party.leader not in party.members:
            raise RestError("Invalid authoritative party snapshot")

    @staticmethod
    def _time(now):
        if not isfinite(now) or now < 0:
            raise RestError("Invalid monotonic timestamp")

    def begin(self, party, requester, hours, now, *, skip_time=False):
        self._validate_party(party)
        self._time(now)
        if requester != party.leader:
            raise RestError("Only the current party leader can start shared rest")
        if not isfinite(hours) or not 1 <= hours <= 24:
            raise RestError("Sleep duration must be between 1 and 24 hours")
        if party.party_id in self._active:
            raise RestError("Party already has an active rest session")
        session = Session(self._next, party, float(hours), now + 60, bool(skip_time))
        self._next += 1
        self._active[party.party_id] = session
        return session.number

    def _get(self, number, party, now):
        self._time(now)
        session = self._active.get(party.party_id)
        if not session or session.number != number:
            raise RestError("Unknown, cancelled or completed rest session")
        if party != session.party:
            self.cancel(number, session.party)
            raise RestError("Membership or leadership changed; start rest again")
        if now >= session.deadline:
            self.cancel(number, party)
            raise RestError("Rest session expired")
        return session

    def report_safe(self, number, party, player, now, *, safe):
        """Adapter reports alive, loaded and out of combat, never client text."""
        session = self._get(number, party, now)
        if player not in party.members:
            raise RestError("Safety report is not from this party")
        if safe:
            session.safe.add(player)
        else:
            session.safe.discard(player)
            session.consent.discard(player)

    def consent_to_skip(self, number, party, player, now, *, agree):
        session = self._get(number, party, now)
        if player not in party.members:
            raise RestError("Consent is not from this party")
        if agree:
            session.consent.add(player)
        else:
            session.consent.discard(player)

    def cancel(self, number, party):
        session = self._active.get(party.party_id)
        if session and session.number == number:
            del self._active[party.party_id]
            return True
        return False

    def complete(self, number, party, now, *, completed_by,
                 actual_hours, connected: FrozenSet[int],
                 current_safe: FrozenSet[int],
                 world_consent: FrozenSet[int] = frozenset()):
        """Call ONLY after a verified, uninterrupted leader rest.

        actual_hours comes from the game adapter, not the request. A shorter
        or interrupted sleep must cancel the transaction, not grant full rest.
        current_safe is rechecked at commit, so old readiness cannot authorize
        benefits or a world-time skip during combat.
        """
        session = self._get(number, party, now)
        if completed_by != party.leader:
            raise RestError("Only verified leader completion can commit rest")
        if (not isfinite(actual_hours) or
                abs(actual_hours - session.hours) > 0.01):
            self.cancel(number, party)
            raise RestError("Interrupted sleep or duration mismatch")
        if not party.members <= connected:
            self.cancel(number, party)
            raise RestError("Party member disconnected during rest")
        if not party.members <= session.safe or not party.members <= current_safe:
            raise RestError("Every teammate must be alive, loaded and out of combat")
        # Party consent alone may never skip time for unrelated online players.
        skip = (session.skip_requested and party.members <= session.consent
                and connected <= world_consent and connected <= current_safe)
        result = Completion(
            number,
            tuple(Benefit(player, session.hours) for player in sorted(party.members)),
            session.hours if skip else 0.0,
        )
        self.cancel(number, party)
        return result

    @property
    def active_count(self):
        return len(self._active)


class ClientRestEffects:
    """Local receipt/menu policy; call from the verified game-thread adapter.

    The adapter must persist receipts per character, scope session IDs to a
    server-instance UUID, and deliver only authenticated server completions.
    Point availability is read AFTER local rest/level-up bookkeeping finishes.
    No player can open another player's menu or transfer points.

    This module does not call Skyrim, Papyrus or Static Skill Leveling itself.
    """
    def __init__(self, player):
        self.player = player
        self._last_completed = 0
        self._pending_menu = False

    def receive(self, completion, *, apply_rest):
        if completion.session <= self._last_completed:
            return False
        benefits = [b for b in completion.benefits if b.player == self.player]
        if len(benefits) != 1:
            raise RestError("Completion must contain this character exactly once")
        hours = benefits[0].hours
        if not isfinite(hours) or not 1 <= hours <= 24:
            raise RestError("Invalid authenticated sleep duration")
        # The game adapter must make this operation transactional with its
        # persisted receipt. Exceptions must not leave a partially applied rest.
        apply_rest(hours)
        self._last_completed = completion.session
        self._pending_menu = True
        return True

    def poll_skill_menu(self, *, bookkeeping_finished, can_open_menu,
                        get_spendable_points, open_skill_menu):
        if not self._pending_menu or not bookkeeping_finished:
            return False
        if not can_open_menu():
            return False
        points = get_spendable_points()
        if not isinstance(points, int) or points < 0:
            raise RestError("Unverified local skill-point availability")
        if points == 0:
            self._pending_menu = False
            return False
        # Reuse the existing SSL entry point; never recompute/award new points.
        # Callback returns True only after the existing menu accepts the open.
        if not open_skill_menu():
            return False
        self._pending_menu = False
        return True
