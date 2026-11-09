"""Generation, identity and wire gates for issue #203 trial-track races."""
import json
import unittest

from worlds.AutoWorld import call_all
from . import setup_multiworld
from .. import ctrAPWorld

from ..destinations import TRIAL_TROPHY_CLASS
from . import CTRTestBase


class TestTrialTrackRacesOff(CTRTestBase):
    pass


class TestSlideTrophyOnly(CTRTestBase):
    options = {"slide_coliseum_races": "trophy_race"}


class TestBothFamilies(CTRTestBase):
    options = {
        "slide_coliseum_races": "trophy_and_ctr_challenge",
        "turbo_track_races": "trophy_and_ctr_challenge",
        "wumpa_check": "per_track",
    }

