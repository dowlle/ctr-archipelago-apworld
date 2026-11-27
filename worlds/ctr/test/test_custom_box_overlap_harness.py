"""Mode coverage of the local LEV audit without third-party files in CI."""
import hashlib
import sys
from types import SimpleNamespace

from tools.check_custom_box_overlaps import audit

from .. import sanity, track_rulings


def fixture(tmp_path, monkeypatch):
    main, relic = tmp_path / "main.lev", tmp_path / "relic.lev"
    main.write_bytes(b"main")
    relic.write_bytes(b"relic")
    main_pin = hashlib.sha256(main.read_bytes()).hexdigest()
    relic_pin = hashlib.sha256(relic.read_bytes()).hexdigest()
    tables = {
        main: [
            SimpleNamespace(model_id=8, position=(0, 0, 0)),
            SimpleNamespace(model_id=92, position=(16, 0, 0)),
        ],
        relic: [SimpleNamespace(model_id=92, position=(400, 0, 0))],
    }
    loader = SimpleNamespace(from_path=lambda path: SimpleNamespace(instances=tables[path]))
    monkeypatch.setitem(sys.modules, "levtool.format", SimpleNamespace(LevFile=loader))
    registry = {"tracks": [{"track_key": "audit-fixture", "revisions": [
        {"revision": "2", "modes": ["arcade", "relic_race"], "files": {"lev": {"sha256": main_pin}}},
    ]}]}
    descriptor = dict(content_id="audit-fixture", revision="2", capabilities={"relic": True},
                      files=[dict(role="lev", sha256=main_pin)],
                      relic_files=[dict(role="lev", sha256=relic_pin)])
    return registry, descriptor, {main_pin: str(main), relic_pin: str(relic)}, main_pin, relic_pin


def test_separate_relic_pin_cannot_hide_a_registry_layout(tmp_path, monkeypatch):
    registry, descriptor, index, main, relic = fixture(tmp_path, monkeypatch)
    report = audit(registry, [descriptor], index)
    assert report["missing"] == []
    assert {row[3:] for row in report["covered"] if row[2] == "relic"} == {(main, main), (main, relic)}
    hit, = report["hits"]
    assert hit[3] == "relic" and hit[-2:] == (16.0, main)


def test_audit_uses_the_inherited_generation_pickup_limit(tmp_path, monkeypatch):
    registry, descriptor, index, _, _ = fixture(tmp_path, monkeypatch)
    reviewed = "a" * 64
    monkeypatch.setitem(track_rulings.REVIEWS, "audit-fixture", [[reviewed, "1"]])
    monkeypatch.setitem(sanity.PICKUP_RULING_COUNTS, reviewed, [0, 0, 0])
    monkeypatch.setattr(sanity, "REVIEWED_PICKUP_PINS", sanity.REVIEWED_PICKUP_PINS | {reviewed})
    report = audit(registry, [descriptor], index)
    assert len(report["covered"]) == 3
    assert report["hits"] == []


def test_a_spot_limited_to_another_pin_is_not_audited_on_this_one(tmp_path, monkeypatch):
    """IM1b: a spot with lev_sha256 exists only on those pins (Country Speedway
    3 and 4 on 1.3.1 only), so the audit of the race LEV leaves it out."""
    from .. import box_spots
    registry, descriptor, index, main, _ = fixture(tmp_path, monkeypatch)
    other = "b" * 64
    spot = dict(number=1, pos=[16, 0, 0], rot_y=0)
    authored = lambda s: dict(doc=dict(track=dict(lev_sha256=[main, other]), spots=[s]))
    monkeypatch.setitem(box_spots.CUSTOM_FILES, "audit-fixture", authored(spot))
    assert audit(registry, [descriptor], index)["hits"]
    monkeypatch.setitem(box_spots.CUSTOM_FILES, "audit-fixture", authored(dict(spot, lev_sha256=[other])))
    assert audit(registry, [descriptor], index)["hits"] == []
