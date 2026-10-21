# LoreRim LAN lab

## Download the all-in-one installer

### [Download LoreRim Together Installer for Windows](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/download/v0.3.0-experimental/LoreRim-Together-Installer.zip)

Download the ZIP above, choose **Extract All**, then open
**Install LoreRim Together.exe** and click **Install** after choosing your
LoreRim folder. The installer handles downloads and all compatibility fixes,
then creates a **Play LoreRim Together** desktop shortcut.

**Use this installer download, not the green Code → Download ZIP button.**
That button downloads developer source files. No Python installation or commands
are needed for the installer. It requires your existing matching LoreRim
5.0.4.8 installation. Keep the setup folder on the same drive as LoreRim.
Large game assets are reused through links; only programs, scripts, plugin
records and settings are copied.

[Release page and download assets](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/tag/v0.3.0-experimental)
· [Simple installation guide](SECOND-PC.md)

**Experimental setup and verification tooling. Not a certified LoreRim multiplayer patch.**

The fast installer creates a multiplayer workspace that shares large static game assets through hard links while keeping programs, scripts, plugin records and settings in private files. It adds the official Skyrim Together Reborn **1.8.3 build for Skyrim 1.6.1170**, and provides strict file-parity checks and a two-client acceptance procedure. It does not claim that connecting means Requiem, combat, quests or scripted systems synchronize correctly.

Initial target: LoreRim 5.0.4.8 / Skyrim 1.6.1170 / portable MO2. Different LoreRim versions need their own assessment. Each PC needs its own licensed game and installed modpack. No game files, mod assets or saves are distributed here.

## Install on the second computer

1. [Download the guided installer ZIP](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/download/v0.3.0-experimental/LoreRim-Together-Installer.zip).
2. Extract it, then double-click **Install LoreRim Together.exe**.
3. Choose the existing LoreRim folder and click **Install**. Setup handles the
   downloads and all compatibility fixes, then creates a desktop play shortcut.

No Python installation or typed commands are needed. Both PCs need matching
LoreRim 5.0.4.8 / Skyrim 1.6.1170. Choose a setup folder on the same drive as LoreRim. The installer checks
the smaller amount of space needed for private files and downloads.
See [SECOND-PC.md](SECOND-PC.md) for joining, or [installer/README.md](installer/README.md)
for installer behavior, validation and building from source. The GitHub **Code →
Download ZIP** option contains source, not the ready-to-use installer.

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
python -m unittest discover -s . -p 'test_*.py' -v
```

Measure basic network RTT with `measure_lan.ps1 -Peer <peer-IP> -Output lan-rtt.csv`. This is ICMP, not game event latency or frame time. TESTING.md separates these measurements.

## Rollback

Exit the lab game, lab MO2 and server, then reopen your original MO2/profile. Programs, scripts and settings are independent; large assets are shared by the fast installer. Do not edit assets or update/regenerate mods through the LAN workspace. Do not copy lab saves back. Retain wanted test evidence before deleting the lab to recover disk space. No automated recursive deletion is included.

## Upstream and licensing

- [STR 1.8.3 release](https://github.com/tiltedphoques/TiltedEvolution/releases/tag/v1.8.3)
- [STR source](https://github.com/tiltedphoques/TiltedEvolution), GPL-3.0-or-later with component exceptions documented upstream
- [Official compatibility FAQ](https://wiki.tiltedphoques.com/tilted-online/general-information/faq)
- [Party and quest playguide](https://wiki.tiltedphoques.com/tilted-online/general-information/playguide)

Original tooling is MIT-licensed. Third-party assets are obtained directly from their owners; the repository grants no right to redistribute them.

## Reproduced startup blockers (2026-10-20)

**Update:** an opt-in, exact-build camera scanner correction is now available and
installed in the test lab. SKSE reports that the camera loads correctly and
continues to later plugins. The subsequent dosemetha hook error is corrected by
the allocation adapter below; its canonical filename is restored. The earlier
rename workaround is recorded in [DOSEMETHA-FIX.md](DOSEMETHA-FIX.md).
The subsequent DynDOLOD allocation failure is corrected by the locally built
adapter in [BSA-MAPPING-FIX.md](BSA-MAPPING-FIX.md). Its latest runtime test loads
DynDOLOD, installs the BSA and Better AltTab hooks, completes initialization and
reaches the LoreRim main menu through Skyrim Together. Player Eyes Blink Fix received the same verified scanner
correction as the camera. All 38 tooling tests and eleven native mapping tests pass.
See [CAMERA-FIX.md](CAMERA-FIX.md) for installation,
rollback, hashes and validation limits. Full camera behavior and multiplayer
remain unverified. The following records the original failure and diagnosis.

On the isolated LoreRim 5.0.4.8 / Skyrim 1.6.1170 host, STR 1.8.3 initially stopped because KiENBExtender.dll could not locate KiHalloc.dll. The loader excludes PATH from DLL search but explicitly searches the launcher directory. `loader_fix.py` now copies the existing effective KiLoader dependency into that directory, verifies its SHA256 and refuses conflicting files. No third-party DLL is distributed. The retry loaded both DLLs; this verifies dependency loading only.

The retry then stopped at Improved Alternate Conversation Camera 1.2.0.0 with `[ERROR] Unknown pattern: 0f28c1f30f5ec60f28f0`. No game menu, connection or gameplay was reached. The camera remains enabled. Do not skip this error and treat that as compatibility.

The follow-up investigation reproduced the error and inspected the installed Improved DLL and live STR image. The requested bytes occur on a PAGE_EXECUTE_READWRITE (`0x40`) page, but this camera scan tests for PAGE_EXECUTE_READ (`0x20`) and skips that page. See [CAMERA-DIAGNOSIS.md](CAMERA-DIAGNOSIS.md) for hashes, disassembly observations, live evidence, limitations and the read-only `camera_probe.py` procedure. This explains the first failed scan; a feature-preserving native repair and later-hook validation remain outstanding. No native patch was applied.

Source references: [STR loader](https://github.com/tiltedphoques/TiltedEvolution/blob/4917189f6ac382e874f9ee735c4fef6a350e449e/Code/immersive_launcher/loader/PathRerouting.cpp), [original camera scanner](https://github.com/NasiRawon/AlternateConversationCamera/blob/aa815816fc38aa85f5e23a186742d931bf99de2b/PatternScanner.h), [installed camera mod page](https://www.nexusmods.com/skyrimspecialedition/mods/68210).

Sixteen tests pass on Windows x64, including byte-preserving dependency staging, refusal to overwrite a different DLL, bounded diagnostic reads and a read-only self-process capture. C++ compilation and two-client gameplay are NOT verified. Existing labs can run `python loader_fix.py <lab-folder>` with all lab processes closed; it requires the lab marker. New setups apply this automatically.

## Large plugin-list connection failure

The first ModPolicy rejection contained empty plugin names after the client
send pool exhausted its capacity. The exact-build correction, native regression
and rollback procedure are recorded in [TRANSPORT-FIX.md](TRANSPORT-FIX.md).
Keep ModPolicy enabled; empty names are not a reason to remove mods.

## JContainers crash on character load

The follow-up crash was a null Lua interpreter during JContainers 4.2.9
initialization. The official 4.2.13.1 memory fix is installed in the isolated
lab, with hash-pinned installation and rollback. The old DLL fails both native
Lua tests under low-address-space pressure; the updated DLL passes both.
See [JCONTAINERS-FIX.md](JCONTAINERS-FIX.md). In-game retry remains pending.

## First accepted local connection

On October 20, 2026 at 23:04:52 Pacific, the server accepted the lab player
with all 3,492 mods while ModPolicy was active. The user screenshot shows
in-world gameplay and “Successfully connected to server.” This verifies
character load and one local client connection. Two-client LAN gameplay and
combat/quest synchronization remain unverified.
