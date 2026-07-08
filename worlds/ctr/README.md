# Crash Team Racing (CTR Archipelago)

An [Archipelago](https://archipelago.gg) Multiworld world for **Crash Team Racing (PSX, 1999)**.

This world targets the native PC client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap), a build of the CTR-tools decompilation that connects to Archipelago directly, in-process. No emulator, no ROM patching. The world handles all randomization (warp-pad requirements and destination shuffle, two-stage requirements, boss/door/gem-cup gating, goals) and hands the client a per-seed configuration through slot data.

The randomization design builds on Icebound777's CTR randomizer (MIT), and this project carries the native path forward with his blessing. The foundational work, and the credit for it, stays with him and Taor.

**Status: in development, not yet released.** The code is public for collaboration and transparency; there is no supported player-facing release yet.

---

## AI Usage Disclosure

CTR Archipelago is developed with AI assistance (Anthropic's Claude, via Claude Code). The short version:

- **AI writes much of the code**, under my direction: randomization and generation logic, the native AP integration, debugging, and review passes.
- **No AI-generated art.** Every tracker icon and in-game marker is rendered from the game's own 3D models. No generated textures, logos, or models.
- **Nothing ships unverified.** Every apworld release passes a full run of Eijebong's Archipelago fuzzer (10/10 check categories across ~14,000 generations; nothing ships red). I playtest every native build in-game on real seeds, and gating logic is verified against the game's actual code, not guessed. The project has a human-reviewed specification and data contract; I don't merge code I haven't understood.
- **Why:** AI lets me actually finish my projects (I have ADHD). Using it is a considered choice, not a careless one.

If AI-assisted development is a dealbreaker for you, that's a fair call to make with the facts in front of you.
