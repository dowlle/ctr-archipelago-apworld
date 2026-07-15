# Crash Team Racing (CTR Archipelago)

An [Archipelago](https://archipelago.gg) Multiworld world for **Crash Team Racing (PSX, 1999)**.

This world targets the native PC client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap), a build of the CTR-tools decompilation that connects to Archipelago directly, in-process. No emulator, no ROM patching. The world handles all randomization (warp-pad requirements and destination shuffle, two-stage requirements, boss/door/gem-cup gating, goals) and hands the client a per-seed configuration through slot data.

The randomization design builds on Icebound777's CTR randomizer (MIT), and this project carries the native path forward with his blessing. The foundational work, and the credit for it, stays with him and Taor.

Releases ship as a pair (client + `ctr.apworld`) on the [client's releases page](https://github.com/dowlle/ctr-native-ap/releases).

**Found a bug?** Please report it on the [client repo's issue tracker](https://github.com/dowlle/ctr-native-ap/issues), whichever half seems at fault - that is the single intake for the whole project. Issues that turn out to be purely generation-side get transferred here, and the link you posted keeps working.

---

## AI Usage Disclosure

CTR Archipelago is developed with AI assistance (Anthropic's Claude, via Claude Code). The short version:

- **AI writes much of the code**, under my direction: randomization and generation logic, the native AP integration, debugging, and review passes.
- **No AI-generated art.** Every tracker icon and in-game marker is rendered from the game's own 3D models. No generated textures, logos, or models.
- **Nothing ships unverified.** Every apworld release passes a full run of Eijebong's Archipelago fuzzer (10/10 check categories across ~14,000 generations; nothing ships red). I playtest every native build in-game on real seeds, and gating logic is verified against the game's actual code, not guessed. The project has a human-reviewed specification and data contract; I don't merge code I haven't understood.
- **Why:** AI lets me actually finish my projects (I have ADHD). Using it is a considered choice, not a careless one.

If AI-assisted development is a dealbreaker for you, that's a fair call to make with the facts in front of you.

---

## License

MIT, matching upstream [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) - see [LICENSE](LICENSE). The requirement logic ports from [Icebound777's CTR randomizer](https://github.com/icebound777/CTR-Randomizer-Standalone) (MIT); his copyright notice is carried in the LICENSE file. The companion game client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap) is a separate codebase and is GPL-3.0 (inherited from the CTR-native decompilation).
