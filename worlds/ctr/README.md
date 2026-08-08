# Crash Team Racing (CTR Archipelago)

An [Archipelago](https://archipelago.gg) Multiworld world for **Crash Team Racing (PSX, 1999)**.

This world targets the native PC client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap), a build of the CTR-tools decompilation that connects to Archipelago directly, in-process. No emulator, no ROM patching. The world handles all randomization (warp-pad requirements and destination shuffle, two-stage requirements, boss/door/gem-cup gating, goals) and hands the client a per-seed configuration through slot data.

The randomization design builds on Icebound777's CTR randomizer (MIT), and this project carries the native path forward with his blessing. The foundational work, and the credit for it, stays with him and Taor.

Releases ship as a pair (client + `ctr.apworld`) on the [client's releases page](https://github.com/dowlle/ctr-native-ap/releases).

**Found a bug?** Please report it on the [client repo's issue tracker](https://github.com/dowlle/ctr-native-ap/issues), whichever half seems at fault - that is the single intake for the whole project. Issues that turn out to be purely generation-side get transferred here, and the link you posted keeps working.

---

## AI usage

I use Claude Code while developing CTR Archipelago. It helps with implementation, debugging, and review, while I make the design decisions and test releases in game. The project does not use AI-generated art. I am disclosing this because I want people to know how the project is made. I have ADHD, and this is one of the tools that helps me turn ideas into finished projects.

---

## License

MIT, matching upstream [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) - see [LICENSE](LICENSE). The requirement logic ports from [Icebound777's CTR randomizer](https://github.com/icebound777/CTR-Randomizer-Standalone) (MIT); his copyright notice is carried in the LICENSE file. The companion game client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap) is a separate codebase and is GPL-3.0 (inherited from the CTR-native decompilation).
