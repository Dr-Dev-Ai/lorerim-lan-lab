# LoreRim LAN lab

**Experimental setup and verification tooling. Not a certified LoreRim multiplayer patch.**

This project preserves an existing LoreRim installation in a separate physical copy, adds the official Skyrim Together Reborn **1.8.3 build for Skyrim 1.6.1170**, and provides strict file-parity checks and a two-client acceptance procedure. It does not claim that connecting means Requiem, combat, quests or scripted systems synchronize correctly.

Initial target: LoreRim 5.0.4.8 / Skyrim 1.6.1170 / portable MO2. Different LoreRim versions need their own assessment. Each PC needs its own licensed game and installed modpack. No game files, mod assets or saves are distributed here.

## Download and prepare the second PC

1. Download the repository ZIP using **Code → Download ZIP**, then extract it.
2. Install Python 3.12 or newer if missing. Locate the actual LoreRim folder containing `ModOrganizer.exe`, `ModOrganizer.ini`, `mods`, `profiles` and `Stock Game`. A Wabbajack download cache alone is not sufficient.
3. Close Skyrim. In PowerShell, open this extracted folder and run:

   ```powershell
   .\Setup-Lab.ps1
   ```

   Enter your existing installation path and a **new, short destination**, such as `D:\LoreRim-LAN\LoreRim`. Allow at least 300 GB free for a typical installation, plus backup space. The script copies profiles/saves to a separate backup, physically copies the installation excluding top-level download/cache/log folders and profile saves, downloads the official runtime-specific STR release, verifies its pinned SHA256, and configures a new **LoreRim LAN Test** profile. It never disables an original mod. It hides STR's two pet-suppression scripts and logo meshes so the installed pet behavior and LoreRim branding keep winning; pet multiplayer remains unverified. This is a lengthy disk copy.

4. Read the generated `str-overrides.json`. It reports loose-file conflicts introduced by STR; archived script conflicts remain a separate audit task.
5. Generate a full manifest on each PC before playing:

   ```powershell
   python .\lancheck.py snapshot 'D:\LoreRim-LAN\LoreRim' 'LoreRim LAN Test' my-manifest.json --full --server-config 'D:\LoreRim-LAN\server\config\STServer.ini'
   ```

6. Exchange only the manifests privately. Compare:

   ```powershell
   python .\lancheck.py compare host-manifest.json guest-manifest.json differences.json
   ```

   Exit 0: parity under the documented scope. Exit 2: explicit mismatches. Exit 3: invalid/incomplete inputs or read failures. Review differences instead of silently removing mods. A fresh local manifest plus a fresh peer manifest is required for meaningful results.

7. Match in-save MCM settings manually, including Requiem, Experience, Static Skill Leveling, Respawn, dodge, Precision and combat settings. File parity cannot verify save-resident state.

For a launch gated by parity:

```powershell
.\start_checked.ps1 -Lab 'D:\LoreRim-LAN\LoreRim' -PeerManifest '.\guest-manifest.json' -HostServer
```

Omit `-HostServer` on the guest. This opens the isolated MO2; run **LoreRim LAN Test**. If asked for the game, select the **lab's** Stock Game/SkyrimSE.exe. Do not select the original or Steam's newer executable.

## LAN configuration

The server is in the lab's sibling `server` folder. Start SkyrimTogetherServer.exe with that working directory. It reads `config/STServer.ini` and `Data/loadorder.txt` there.

- UDP port 10578, two-player limit, public listing disabled.
- Initial lab password `LoreRimLab`; change it if desired and use matching intended server configuration files for preflight.
- Host joins `127.0.0.1:10578`; guest joins `<host-LAN-IPv4>:10578` through F2/right Ctrl.
- Router forwarding is unnecessary for same-LAN play. A firewall rule, if needed, should be scoped to this server executable, UDP 10578, Private profile and local subnet. Scripts do not alter firewall rules.
- Only new disposable profile-local saves. Complete the starting sequence and mod initialization before connecting. Create one party; retain its leader and let that player advance quest dialogue/items.
- STR's death handler and vanilla combat XP sharing are disabled to avoid competing with LoreRim's installed systems. Timescale is read from Requiem's effective settings; difficulty from the source profile. These configuration choices are not proof of synchronization.

## What has and has not been verified

The original test host completed installation inspection, physical isolation, upstream archive checksum verification, preflight automated tests and dedicated-server startup with mod checking enabled. **Actual two-client gameplay has not been verified.** No custom native synchronization patch is provided. Official upstream C++ binaries are downloaded, not locally compiled by this project.

See [TESTING.md](TESTING.md) for combat, animation, damage, loot, quests, transitions, deaths, reconnects, save/reload and performance procedures. Record expected behavior, observations and evidence. Compilation, server startup and connecting are distinct milestones.

Upstream includes MCO/TK Dodge behavior definitions, but that does not establish Precision collision, dodge invulnerability, SCAR AI, Requiem perks/scripts or death-alternative correctness. SmoothCam, alternate conversation cameras and KiLoader are particular launch-risk candidates. Never disable those silently to claim full compatibility. A reduced-feature solution requires an explicit decision.

The manifest hashes the effective loose-file view, opaque archives, Root Builder overlay, runtime and profile configuration; full mode includes all effective assets. It does not resolve archive-internal script precedence, audit native hooks, inspect MCM state inside saves or authenticate a hostile peer. Runtime logs/caches can create conservative mismatches; review them explicitly. Incomplete audit snapshots cannot pass full parity checks.

Run tooling tests with:

```powershell
python -m unittest discover -s . -p test_lancheck.py -v
```

Measure basic network RTT with `measure_lan.ps1 -Peer <peer-IP> -Output lan-rtt.csv`. This is ICMP, not game event latency or frame time. TESTING.md separates these measurements.

## Rollback

Exit the lab game, lab MO2 and server, then reopen your original MO2/profile. Original files are independent; do not copy lab saves back. Retain wanted test evidence before deleting the lab to recover disk space. No automated recursive deletion is included.

## Upstream and licensing

- [STR 1.8.3 release](https://github.com/tiltedphoques/TiltedEvolution/releases/tag/v1.8.3)
- [STR source](https://github.com/tiltedphoques/TiltedEvolution), GPL-3.0-or-later with component exceptions documented upstream
- [Official compatibility FAQ](https://wiki.tiltedphoques.com/tilted-online/general-information/faq)
- [Party and quest playguide](https://wiki.tiltedphoques.com/tilted-online/general-information/playguide)

Original tooling is MIT-licensed. Third-party assets are obtained directly from their owners; the repository grants no right to redistribute them.

## Reproduced startup blockers (2026-10-20)

On the isolated LoreRim 5.0.4.8 / Skyrim 1.6.1170 host, STR 1.8.3 initially stopped because KiENBExtender.dll could not locate KiHalloc.dll. The loader excludes PATH from DLL search but explicitly searches the launcher directory. `loader_fix.py` now copies the existing effective KiLoader dependency into that directory, verifies its SHA256 and refuses conflicting files. No third-party DLL is distributed. The retry loaded both DLLs; this verifies dependency loading only.

The retry then stopped at Improved Alternate Conversation Camera 1.2.0.0 with `[ERROR] Unknown pattern: 0f28c1f30f5ec60f28f0`. No game menu, connection or gameplay was reached. The camera remains enabled. Do not skip this error and treat that as compatibility.

The smallest feature-preserving next fix is to correct the camera's pattern-scan/module-range handling or its specific conflicting hook, after confirming which fails under STR's mapped executable. The older original camera source uses GetModuleHandle(0), GetModuleInformation and executable-page scanning; it is not confirmed identical to the installed Improved 1.2 binary. This is a diagnostic hypothesis, not a verified replacement. Matching source, native build tools and binary/debugger verification are still needed. Do not apply guessed offsets or remove the camera silently.

Source references: [STR loader](https://github.com/tiltedphoques/TiltedEvolution/blob/4917189f6ac382e874f9ee735c4fef6a350e449e/Code/immersive_launcher/loader/PathRerouting.cpp), [original camera scanner](https://github.com/NasiRawon/AlternateConversationCamera/blob/aa815816fc38aa85f5e23a186742d931bf99de2b/PatternScanner.h), [installed camera mod page](https://www.nexusmods.com/skyrimspecialedition/mods/68210).

Eight automated tooling tests pass, including byte-preserving dependency staging and refusal to overwrite a different DLL. C++ compilation and two-client gameplay are NOT verified. Existing labs can run `python loader_fix.py <lab-folder>` with all lab processes closed; it requires the lab marker. New setups apply this automatically.
