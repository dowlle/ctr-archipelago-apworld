from io import StringIO

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
    assert "  N. Sanity Beach / Crash Cove Warp Pad: Crash Cove (Free) | Stage 2: 1 Key" in rows
    assert "  Cups Room / Red Cup Warp Pad: Red Gem Cup (4 Red CTR Tokens) | Hub: 2 Keys" in rows
    assert ("  Gem Stone Valley / Turbo Track Warp Pad: Turbo Track (5 Different Gems) "
            "| Hub: 1 Key | Stage 2: 2 Keys") in rows
    assert "  Lost Ruins / Papu Papu Garage: Papu's Pyramid (1 Key + 8 Trophies)" in rows
    oxide, = [line for line in rows if "N. Oxide Garage:" in line]
    assert "Challenge: Oxide Station (4 Keys) | Final Challenge:" in oxide
    assert "(5 Sapphire Relics or 5 Gold Relics)" in oxide


def test_randomized_second_stage_names_the_relic_tier():
    text = _spoiler({"accessibility": "full"})
    assert ("  Gem Stone Valley / Slide Coliseum Warp Pad: Cortex Castle (10 Any Relics) "
            "| Hub: 1 Key | Stage 2: 5 Gold Relics\n") in text


def test_custom_track_cups_arenas_and_manual_gates():
    options = cup_options(4)
    options["content_pool"]["crystals"]["count"] = 2
    options["content_pool"]["required_entries"] = ["custom/baby-t-park/1.0.2"]
    options["warp_pad_rules"] = {
        "Crash Cove": {"item": "free", "count": 0},
        "Dingo Canyon": {"item": "Gold Relic", "count": 1},
    }
    text = _spoiler(options)
    assert any("Crash Cove Warp Pad:" in line and line.endswith("(Free)") for line in text.splitlines())
    assert any("Dingo Canyon Warp Pad:" in line and line.endswith("(1 Gold Relic) | Hub: 1 Key")
               for line in text.splitlines())
    assert "Warp Pad: Baby T Park (" in text
    assert any("Warp Pad:" in line and " Crystal Challenge (" in line for line in text.splitlines())
    assert any("Warp Pad:" in line and " Cup (" in line and " Gem Cup (" not in line
               for line in text.splitlines())
