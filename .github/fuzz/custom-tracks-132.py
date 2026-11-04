#!/usr/bin/env python3
"""Write the meta of the content-plan-132 arm: content-plan-vanilla-meta.yaml with
130 made-up tracks added to its two, so a seed lists the 132 a YAML may hold
some past slot 32 on their own pads, and with more cups, so
the seed races more tracks. The file pins name no real files: generation never
reads them.
usage: custom-tracks-132.py <vanilla meta> <output>"""
import sys

source, target = sys.argv[1:3]
TRACK = """    - id: package/fuzz-{n:03d}/1.0
      content_id: fuzz-{n:03d}
      uuid: 0f0e0d0c-0b0a-4908-8706-{n:012x}
      revision: "1.0"
      display_name: Fuzz Track {n:03d}
      author: Fixture Author
      laps: 3
      capabilities: {{time_trial: true, arcade: true, relic: {relic}, ctr_tokens: {letters}, wumpa: {wumpa}}}
{relic_targets}      files:
        - {{role: lev, sha256: {lev:064x}, bytes: 1234567, format: ctr-lev, format_version: 1}}
        - {{role: vrm, sha256: {vrm:064x}, bytes: 458808, format: ctr-vrm, format_version: 1}}
      evidence: []
"""
TARGETS = "      relic_targets: {sapphire: 96000, gold: 86400, platinum: 76800}\n"


def track(n):
    relic = n % 3 == 0
    return TRACK.format(n=n, relic="true" if relic else "false", letters="true" if n % 2 else "false",
                        wumpa="true" if n % 5 else "false", relic_targets=TARGETS if relic else "",
                        lev=0xa000 + n, vrm=0xb000 + n)


with open(source) as handle:
    lines = handle.read().split("\n")
required = [f"fuzz-{n:03d}" for n in (40, 90, 130)]
out = []
for line in lines:
    if line.startswith("  required_entries:"):
        out.append("".join(track(n) for n in range(1, 131)).rstrip("\n"))
        out.append("  required_entries: [baby-t-park, " + ", ".join(required) + "]")
    elif line.startswith("  cup_count:"):
        out.append("  cup_count: {5: 2, 9: 1, 13: 1}")
    else:
        out.append(line)
with open(target, "w") as handle:
    handle.write("\n".join(out))
