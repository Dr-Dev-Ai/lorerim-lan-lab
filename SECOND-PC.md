# Install LoreRim Together

You already need the same LoreRim 5.0.4.8 installation as the host.

1. [Download the installer ZIP](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/download/v0.2.0-experimental/LoreRim-Together-Installer.zip).
2. Right-click it and choose **Extract All**. Open the extracted folder.
3. Double-click **Install LoreRim Together.exe**.
4. The installer should find LoreRim. If it does not, click **Browse** and select
   the folder containing **ModOrganizer.exe**.
5. Choose a drive with room for a separate LoreRim copy and click **Install**.
   Close Skyrim and Mod Organizer first. Leave the installer open while it copies.
6. When it says **Ready to play**, use the new **Play LoreRim Together** desktop shortcut.

That is the complete installation. Setup handles the downloads, runtime and
all compatibility fixes. No commands or separate Python installation are needed.
Your original LoreRim stays separate. The copy can take a long time.

## Join the game

1. Open **Play LoreRim Together** from the desktop.
2. Create or load your own lab character. Wait for the mods to finish starting.
3. Press **F2**, then Connect.
4. On your current home network, enter **10.0.0.250:10578**.
5. Enter password **LoreRimLab**.
6. Join the host's party through Player Manager.

The first computer must have the server running. The host computer uses
127.0.0.1:10578; the second computer uses the host address shown above.
If the host's LAN address changes, enter its new address instead.

## If something goes wrong

Click **Open setup log** and send the log back for help. If a download or copy
was interrupted, click **Try again**. Do not delete the partial installation;
the installer can resume it. If the destination is too full, choose another drive.

The initial host test successfully loaded a character and connected with all
3,492 plugins. Two-computer combat and quest synchronization still need testing.
Technical details and validation are in [installer/README.md](installer/README.md).
