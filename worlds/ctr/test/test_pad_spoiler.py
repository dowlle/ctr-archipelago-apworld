from io import StringIO

from .. import content_item_pool, pad_spoiler
from .test_content_cups import cup_options
from .test_content_plan import make_world


def _spoiler(options, seed=420):
    output = StringIO()
    make_world(options, seed=seed).write_spoiler(output)
    return output.getvalue()


def test_vanilla_pad_requirements_and_boss_garages():
    text = _spoiler({
        "pad_placement": "vanilla",
        "warppad_unlock_requirements": "vanilla",
        "oxide_final_challenge_unlock": "any_relic_type",
        "oxide_final_challenge_relic_count": 5,
    })
    assert "CTR warp-pad unlock requirements (ContentPlan):" in text
    assert "CTR independent content/item plan:" not in text
    assert "Original from-pool starts:" in text
    rows = [line for line in text.splitlines() if " Warp Pad:" in line or " Garage:" in line]
    assert len(rows) == 32
    assert ("  N. Sanity Beach / Crash Cove Warp Pad: Crash Cove (Free) "
            "| Stage 2: 1 Key | Later races: win the Trophy Race") in rows
    assert "  Cups Room / Red Cup Warp Pad: Red Gem Cup (4 Red CTR Tokens) | Hub: 2 Keys" in rows
    assert ("  Gem Stone Valley / Turbo Track Warp Pad: Turbo Track (5 Different Gems) "
            "| Hub: 1 Key | Stage 2: 2 Keys") in text
    assert "  Lost Ruins / Papu Papu Garage: Papu's Pyramid (8 Trophies) | Hub: 1 Key" in rows
    oxide, = [line for line in rows if "N. Oxide Garage:" in line]
    assert "Challenge: Oxide Station (4 Keys) | Final Challenge:" in oxide
    assert "(5 Sapphire Relics or 5 Gold Relics)" in oxide
    assert "win N. Oxide's Challenge" in oxide


def test_randomized_second_stage_names_the_relic_tier():
    text = _spoiler({"accessibility": "full"})
    row, = [line for line in text.splitlines() if "/ Slide Coliseum Warp Pad:" in line]
    assert "Cortex Castle (" in row
    assert "| Hub: 1 Key | Stage 2: 5 Gold Relics" in row


def test_custom_track_cups_arenas_and_manual_gates():
    options = cup_options(4)
    options["content_pool"]["crystals"]["count"] = 2
    options["content_pool"]["required_entries"] = ["custom/baby-t-park/1.0.2"]
    options["warp_pad_rules"] = {
        "Crash Cove": {"item": "free", "count": 0},
        "Dingo Canyon": {"item": "Gold Relic", "count": 1},
    }
    text = _spoiler(options)
    assert any("Crash Cove Warp Pad:" in line and "(Free)" in line for line in text.splitlines())
    assert any("Dingo Canyon Warp Pad:" in line and "(1 Gold Relic) | Hub: 1 Key" in line
               for line in text.splitlines())
    assert "Warp Pad: Baby T Park (" in text
    assert any("Warp Pad:" in line and " Crystal Challenge (" in line for line in text.splitlines())
    assert any("Warp Pad:" in line and " Cup (" in line and " Gem Cup (" not in line
               for line in text.splitlines())


def test_single_stage_and_optional_oxide():
    text = _spoiler({
        "pad_placement": "vanilla",
        "warppad_unlock_requirements": "vanilla",
        "two_stage_density": "off",
        "oxide_goal": "101_percent",
        "oxide_1_optional": "optional",
        "goal_wumpa": 750,
    })
    assert "Crash Cove Warp Pad: Crash Cove (Free) | Later races: win the Trophy Race" in text
    assert "Stage 2:" not in text
    oxide, = [line for line in text.splitlines() if "N. Oxide Garage:" in line]
    assert "750 Wumpa Fruit banked in total" in oxide
    assert "win N. Oxide's Challenge" not in oxide
    assert "Challenge: Oxide Station (4 Keys) [offered until won or Final Challenge opens]" in oxide


def test_any_percent_companion_gates_appear_on_first_challenge():
    text = _spoiler({"oxide_goal": "any_percent", "bosses_required_goal": 2, "gems_required_goal": 2})
    oxide, = [line for line in text.splitlines() if "N. Oxide Garage:" in line]
    first, final = oxide.split(" | ")
    assert "4 Keys + 2 Boss Wins + 2 Different Gems" in first
    assert "18 Sapphire Relics + win N. Oxide's Challenge" in final
    assert "Boss Wins" not in final
    assert "Different Gems" not in final


def test_relic_first_race_uses_lowest_tier_with_a_check():
    pad_id = "pad:3"
    plan = {
        "pad_requirements": {},
        "pads": [{"id": pad_id, "mode_gates": [{"mode": "relic"}, {"mode": "trophy"}]}],
        "checks": [
            {"kind": "relic", "location": 1, "routes": [{"own_pad_id": pad_id, "award": "platinum"}]},
            {"kind": "relic", "location": 2, "routes": [{"own_pad_id": pad_id, "award": "gold"}]},
        ],
    }
    assert pad_spoiler._first_race_wins(plan) == {pad_id: "meet the Gold Relic time"}


def test_partial_family_gates_show_which_items_count():
    items = content_item_pool.ITEMS
    relics = {"op": "sum", "count": 2, "items": [items["Sapphire Relic"], items["Gold Relic"]]}
    gems = {"op": "distinct", "count": 2, "items": [items["Red Gem"], items["Green Gem"]]}
    assert pad_spoiler._requirement(relics) == "2 Any Relics (Sapphire Relic / Gold Relic)"
    assert pad_spoiler._requirement(gems) == "2 Different Gems (Red Gem / Green Gem)"
