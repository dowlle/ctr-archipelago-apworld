"""DeathLink send conditions (0.2.3): the death_link_send bitmask.

slot_data ctr_options.death_link_send is an int bitmask, 1 mask_grab,
2 weapon_hit, 4 race_loss. While the option is left at its default it follows
death_link (the legacy coupling); an explicit list, including an empty one,
overrides it. The bit values are a contract with native.
"""

from ..Options import DeathLink, DeathLinkSend
from . import CTRTestBase

KEY = "death_link_send"


def _emitted(test) -> int:
    return test.world.fill_slot_data()["ctr_options"][KEY]


class TestBits(CTRTestBase):
    run_default_tests = False
    options = {}

    def test_bit_values_are_stable(self):
        from ..Options import DL_SEND_BITS
        self.assertEqual(DL_SEND_BITS, {"mask_grab": 1, "weapon_hit": 2,
                                        "race_loss": 4})


    def test_from_any_distinguishes_unset_from_empty(self):
        # A YAML that omits the option gets the class default (sentinel); an
        # explicit empty list is a real empty set.
        self.assertEqual(DeathLinkSend.from_any([]).value, set())
        self.assertEqual(DeathLinkSend.from_any(["mask_grab"]).value,
                         {"mask_grab"})
        self.assertEqual(DeathLinkSend.default, frozenset({"follow_death_link"}))

    def test_mixed_sentinel_drops_the_sentinel(self):
        opt = DeathLinkSend.from_any(["follow_death_link", "mask_grab"])
        opt.verify(self.multiworld.worlds[1], "P", None)
        self.assertEqual(set(opt.value), {"mask_grab"})
        self.assertEqual(opt.send_mask(0), 1)

    def test_unknown_value_is_rejected(self):
        with self.assertRaises(Exception):
            DeathLinkSend.from_any(["bogus"]).verify(
                self.multiworld.worlds[1], "P", None)


class TestLegacyFollow(CTRTestBase):
    """Old YAMLs (option unset) keep the old coupling."""

    run_default_tests = False
    options = {}

    def _check(self, death_link, expected):
        self.world.options.death_link.value = death_link
        self.assertEqual(_emitted(self), expected)




class TestExplicitOverrides(CTRTestBase):
    """A listed set replaces the legacy coupling."""

    run_default_tests = False
    options = {"death_link": "any_hit"}

    def _set(self, keys):
        self.world.options.death_link_send.value = set(keys)


    def test_each_bit_and_combinations(self):
        for keys, want in [(["mask_grab"], 1), (["weapon_hit"], 2),
                           (["race_loss"], 4), (["weapon_hit", "race_loss"], 6),
                           (["mask_grab", "weapon_hit", "race_loss"], 7)]:
            self._set(keys)
            self.assertEqual(_emitted(self), want, keys)

    def test_send_without_receive_effect_change(self):
        # Sending race_loss only, while receiving as race_loss.
        self.world.options.death_link.value = DeathLink.option_race_loss
        self._set(["race_loss"])
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co[KEY]), (3, 4))


class TestGeneratesFromRealOptions(CTRTestBase):
    """End to end through option parsing, not by poking .value."""

    options = {"death_link": "mask_reset", "death_link_send": ["weapon_hit"]}

    def test_emitted(self):
        self.assertEqual(_emitted(self), 2)


class TestGeneratesEmptyList(CTRTestBase):
    options = {"death_link": "mask_reset", "death_link_send": []}

    def test_emitted(self):
        self.assertEqual(_emitted(self), 0)


class TestNoOneWayDeathLink(CTRTestBase):
    """Ruling of 2026-09-30: sending implies receiving. A send trigger with
    DeathLink off turns DeathLink on as mask_reset, with a notice."""

    options = {"death_link": "off", "death_link_send": ["weapon_hit"]}

    def test_off_with_send_resolves_to_mask_reset(self):
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co[KEY]), (1, 2))


class TestOffWithoutSend(CTRTestBase):
    options = {"death_link": "off", "death_link_send": []}

    def test_both_zero(self):
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co[KEY]), (0, 0))


class TestOffUnsetStaysOff(CTRTestBase):
    """A legacy YAML with DeathLink off and no death_link_send is unchanged."""

    options = {"death_link": "off"}



class TestReceiveOnlyStaysAllowed(CTRTestBase):
    options = {"death_link": "race_loss", "death_link_send": []}

    def test_receive_only(self):
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co[KEY]), (3, 0))


class TestResolutionNotice(CTRTestBase):
    run_default_tests = False
    options = {}

