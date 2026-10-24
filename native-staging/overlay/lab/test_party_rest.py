import unittest
from dataclasses import replace

from party_rest import Party, PartyRest, RestError, ClientRestEffects


class RestTests(unittest.TestCase):
    def setUp(self):
        self.party = Party(10, 1, 1, frozenset({1, 2}))
        self.rest = PartyRest()

    def begin(self, **kwargs):
        n = self.rest.begin(self.party, 1, 8, 0, **kwargs)
        for p in self.party.members:
            self.rest.report_safe(n, self.party, p, 1, safe=True)
        return n

    def complete(self, n, **kwargs):
        args = dict(completed_by=1, actual_hours=8,
                    connected=self.party.members, current_safe=self.party.members)
        args.update(kwargs)
        return self.rest.complete(n, self.party, 5, **args)

    def test_same_leader_duration_for_both(self):
        result = self.complete(self.begin())
        self.assertEqual([(b.player, b.hours) for b in result.benefits],
                         [(1, 8), (2, 8)])
        self.assertEqual(result.advance_hours, 0)

    def test_nonleader_cannot_request_or_complete(self):
        with self.assertRaises(RestError):
            self.rest.begin(self.party, 2, 8, 0)
        n = self.begin()
        with self.assertRaises(RestError):
            self.complete(n, completed_by=2)

    def test_membership_change_cancels(self):
        n = self.begin()
        changed = replace(self.party, revision=2, members=frozenset({1, 3}))
        with self.assertRaises(RestError):
            self.rest.report_safe(n, changed, 1, 2, safe=True)
        self.assertEqual(self.rest.active_count, 0)

    def test_leader_change_cancels(self):
        n = self.begin()
        with self.assertRaises(RestError):
            self.rest.report_safe(n, replace(self.party, leader=2), 2, 2, safe=True)
        self.assertEqual(self.rest.active_count, 0)

    def test_disconnect_and_interrupted_rest_do_not_award(self):
        for overrides in (dict(connected=frozenset({1})), dict(actual_hours=1)):
            self.setUp()
            n = self.begin()
            with self.assertRaises(RestError):
                self.complete(n, **overrides)
            self.assertEqual(self.rest.active_count, 0)

    def test_recheck_combat_at_commit(self):
        with self.assertRaises(RestError):
            self.complete(self.begin(), current_safe=frozenset({1}))

    def test_timeout_and_replay(self):
        n = self.begin()
        with self.assertRaises(RestError):
            self.rest.report_safe(n, self.party, 1, 60, safe=True)
        n = self.begin()
        self.complete(n)
        with self.assertRaises(RestError):
            self.complete(n)

    def test_skip_requires_everyones_consent(self):
        n = self.begin(skip_time=True)
        for p in self.party.members:
            self.rest.consent_to_skip(n, self.party, p, 2, agree=True)
        self.assertEqual(self.complete(n, world_consent=self.party.members).advance_hours, 8)

    def test_missing_consent_grants_rest_without_skipping(self):
        self.assertEqual(self.complete(self.begin(skip_time=True)).advance_hours, 0)

    def test_other_party_is_never_time_skipped_without_consent(self):
        n = self.begin(skip_time=True)
        for p in self.party.members:
            self.rest.consent_to_skip(n, self.party, p, 2, agree=True)
        result = self.complete(n, connected=frozenset({1, 2, 3}),
                               current_safe=frozenset({1, 2, 3}),
                               world_consent=self.party.members)
        self.assertEqual(result.advance_hours, 0)
        self.assertEqual({b.player for b in result.benefits}, {1, 2})

    def test_invalid_durations(self):
        for hours in (0, -1, 25, float('nan'), float('inf')):
            with self.assertRaises(RestError):
                self.rest.begin(self.party, 1, hours, 0)


class ClientMenuTests(unittest.TestCase):
    setUp = RestTests.setUp
    begin = RestTests.begin
    complete = RestTests.complete

    def delivery(self):
        return self.complete(self.begin())

    def test_each_player_checks_own_points(self):
        result = self.delivery()
        opened = []
        rested = []
        for player, points in ((1, 0), (2, 7)):
            client = ClientRestEffects(player)
            client.receive(result, apply_rest=lambda h: rested.append((player, h)))
            client.poll_skill_menu(
                bookkeeping_finished=True, can_open_menu=lambda: True,
                get_spendable_points=lambda: points,
                open_skill_menu=lambda: opened.append(player) or True)
        self.assertEqual(rested, [(1, 8), (2, 8)])
        self.assertEqual(opened, [2])

    def test_waits_for_bookkeeping_and_safe_ui(self):
        client = ClientRestEffects(1)
        client.receive(self.delivery(), apply_rest=lambda h: None)
        opened = []
        def poll(done, safe):
            return client.poll_skill_menu(
                bookkeeping_finished=done, can_open_menu=lambda: safe,
                get_spendable_points=lambda: 3,
                open_skill_menu=lambda: opened.append(1) or True)
        self.assertFalse(poll(False, True))
        self.assertFalse(poll(True, False))
        self.assertTrue(poll(True, True))
        self.assertFalse(poll(True, True))
        self.assertEqual(opened, [1])

    def test_duplicate_delivery_does_not_reapply_or_reopen(self):
        client = ClientRestEffects(1)
        result = self.delivery()
        calls = []
        self.assertTrue(client.receive(result, apply_rest=calls.append))
        self.assertFalse(client.receive(result, apply_rest=calls.append))
        self.assertEqual(calls, [8])

    def test_no_points_no_menu(self):
        client = ClientRestEffects(1)
        client.receive(self.delivery(), apply_rest=lambda h: None)
        def forbidden():
            self.fail("A character without points must not get a menu")
        self.assertFalse(client.poll_skill_menu(
            bookkeeping_finished=True, can_open_menu=lambda: True,
            get_spendable_points=lambda: 0, open_skill_menu=forbidden))

    def test_failed_open_retries_without_reapplying_rest(self):
        client = ClientRestEffects(1)
        applied = []
        client.receive(self.delivery(), apply_rest=applied.append)
        def poll(opener):
            return client.poll_skill_menu(
                bookkeeping_finished=True, can_open_menu=lambda: True,
                get_spendable_points=lambda: 2, open_skill_menu=opener)
        self.assertFalse(poll(lambda: False))
        self.assertTrue(poll(lambda: True))
        self.assertEqual(applied, [8])


if __name__ == '__main__':
    unittest.main()
