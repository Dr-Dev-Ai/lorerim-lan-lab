# Install the second LoreRim LAN computer

This guide reproduces the host setup that successfully loaded a character and
connected to the server on October 20, 2026 at 23:04:52 Pacific. The server
accepted all 3,492 plugins with ModPolicy enabled. Two-computer gameplay,
combat and quest synchronization have not yet been verified.

## What to transfer

Use the complete `LoreRim-Startup-Fix.zip` package supplied with the chat,
including its `adapter` folder. A GitHub source ZIP alone does not include the
built adapter. Extract the package into a short folder, for example
`D:\LoreRim-LAN-Tools`. It contains our tooling and adapter, not LoreRim itself.

The second PC needs Windows, its own licensed Skyrim installation, Python
3.12 or newer, and the same installed **LoreRim 5.0.4.8 / Skyrim 1.6.1170**
modpack. Do not substitute a different LoreRim release or current Steam runtime.
Allow space for a separate physical lab copy in addition to the existing
installation. The setup script excludes the download cache and existing saves.

## Create the isolated lab and apply every fix

Close the second PC's game and MO2. Open PowerShell in the extracted tools
folder. The example below assumes its normal LoreRim installation is
`D:\Modlists\LoreRim`; replace that source path with the actual folder
containing ModOrganizer.exe. The destination must be a new folder.

```powershell
.\Setup-Lab.ps1 -Source 'D:\Modlists\LoreRim' -Destination 'D:\LoreRim-LAN\LoreRim'
```

After setup finishes successfully, apply these fixes from the same tools folder:

```powershell
python .\camera_fix.py 'D:\LoreRim-LAN\LoreRim'
python .\bsa_guard_fix.py 'D:\LoreRim-LAN\LoreRim' --adapter '.\adapter\BSAMemoryMap.dll'
python .\blink_fix.py 'D:\LoreRim-LAN\LoreRim'
python .\alttab_fix.py 'D:\LoreRim-LAN\LoreRim'
python .\transport_fix.py 'D:\LoreRim-LAN\LoreRim'
python .\jcontainers_update.py 'D:\LoreRim-LAN\LoreRim'
```

Run each command only after the preceding command succeeds. If an installer
reports an unsupported hash or other error, stop and retain the error for
review; it means that computer does not match the tested files. Do not force
it or disable mods. The JContainers command downloads and verifies the official
4.2.13.1 package. The dependency loader fix is already applied by Setup-Lab.
Do not apply the superseded dosemetha filename workaround.

If Windows prevents running the PowerShell setup script, report the exact
message so the setup can be handled through an appropriate local method.

## Match the two installations

Before playing together, close both game clients and create full manifests.
On the host, use its actual lab path and host server config. On the guest:

```powershell
python .\lancheck.py snapshot 'D:\LoreRim-LAN\LoreRim' 'LoreRim LAN Test' guest-manifest.json --full --server-config 'D:\LoreRim-LAN\server\config\STServer.ini'
```

Exchange manifests privately and compare them from the tools folder:

```powershell
python .\lancheck.py compare host-manifest.json guest-manifest.json differences.json
```

Review any differences; do not remove mods just to clear the check. Match
in-save MCM settings as well, since manifests cannot inspect those settings.
Use separate disposable lab characters rather than regular playthrough saves.

## Launch and connect

1. Open **D:\LoreRim-LAN\LoreRim\ModOrganizer.exe** on the second PC.
2. Select the **LoreRim LAN Test** profile and **LoreRim LAN Test** executable,
   then click Run. If prompted for Skyrim, choose the lab's
   `Stock Game\SkyrimSE.exe`.
3. Create the second player's own character. Finish the starting sequence
   and wait for Requiem/mod initialization before connecting.
4. Leave the dedicated server running on the first PC. The second PC does
   not need to start its generated server.
5. Press **F2** (or right Ctrl), choose Connect, enter the **first PC's LAN IP
   followed by :10578**, and use password **LoreRimLab**.
6. The host creates a party; the second player joins it through Player Manager.
   Keep one party leader for quest progression, then follow TESTING.md.

For this host at the time of writing, the Ethernet address is
**10.0.0.250**, so the guest joins **10.0.0.250:10578**. The host itself joins
**127.0.0.1:10578**. If the host's address changes, use its new Ethernet IPv4
address. 127.0.0.1 on the guest would point to the guest itself.

For same-LAN play, router port forwarding is unnecessary. If the guest times
out, check that the server is running and that the host firewall allows its
server executable on UDP 10578 for the private local network. No firewall
settings were changed by this package.

## Rollback

The original installation remains separate. Close the lab game/MO2 and reopen
the original MO2 to play normally. Each fix has its own restore procedure in
its accompanying guide; retain the lab backup folders. Do not copy lab saves
into your regular playthrough.
