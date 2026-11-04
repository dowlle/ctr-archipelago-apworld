"""Universal Tracker fuzz hook for CTR, comparing checks by location id.

The pinned Universal Tracker hook (worlds.tracker.fuzzer_hook) compares the
server's and the tracker's in-logic checks by location name. CTR renames
generic-slot custom-track checks inside the tracker's regenerated world to
their room title (#306 B+, custom_track_presentation.apply_ut_room_names), so
the tracker lists 'Fuzz Fixture Loop: Trophy Race' where the server has
'Custom Track 2: Trophy Race' under the same id. A real tracker session checks
locations off by id, so the rename is display only, but the name comparison
reports every renamed check as missing.

This hook runs the upstream hook unchanged and only translates the tracker's
in-logic names back to the server's names through their location id before
the comparison. A name the tracker cannot resolve to an id passes through
unchanged, so a check the tracker lacks or places out of logic still fails.

CI copies this file to archipelago/hooks/ctr_ut_hook.py; use it as
--hook hooks.ctr_ut_hook:Hook with the tracker world installed.
"""

from worlds.tracker.fuzzer_hook import Hook as TrackerHook


class Hook(TrackerHook):
    server_names: dict

    def before_generate(self, args):
        super().before_generate(args)
        self.server_names = {}
        core = self.ut_core
        update = core.updateTracker

        def update_by_id():
            ret = update()
            if core.multiworld is None or core.player_id is None:
                return ret
            cache = core.multiworld.regions.location_cache[core.player_id]
            translated = []
            for name in ret.in_logic_locations:
                location = cache.get(name)
                address = getattr(location, "address", None)
                translated.append(self.server_names.get(address, name))
            return ret._replace(in_logic_locations=translated)

        core.updateTracker = update_by_id

    def after_generate(self, mw, output_path):
        if mw is not None and len(mw.worlds) == 1:
            self.server_names = {
                location.address: location.name
                for location in mw.get_locations(1)
                if location.address is not None
            }
        return super().after_generate(mw, output_path)
