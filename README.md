# WARDOGS Range Finder
**Quick Start & How to Use**

The WARDOGS Range Finder calculates the straight-line distance between two locations on the in-game map, displaying the result in metres.

## Getting Started

1. Ensure `RUN ME.vbs` and `wd_rf.py` are located in the same folder.
2. Once installation is complete, double-click **RUN ME.vbs** to launch the Range Finder.
3. Leave the Range Finder running while playing WARDOGS.

**Note:** Python installation is only required once. If a compatible version is already installed, the installer will skip installation. After the initial setup, simply use **RUN ME.vbs** to launch the Range Finder.

*Requires Windows. An internet connection is required if Python needs to be downloaded.*

## Step 1 — Set Point A (Current Location)

1. While in-game, open your map.
2. Right-click your current location and select **Mark Coordinates**. The game will place the coordinates in the in-game chat input.
3. Press **Ctrl + A** to highlight the coordinates.
4. Press **Ctrl + C** to copy them.
5. Press **F9** to load the copied coordinates into the Range Finder's **Current position** field.

## Step 2 — Set Point B (Destination)

1. Open your map, right-click your intended destination, and select **Mark Coordinates**.
2. The destination coordinates will appear in the chat input.
3. Press **Ctrl + A**, followed by **Ctrl + C**, to copy the new coordinates.
4. Press **F10** to load them into the **Destination** field.

## Step 3 — Read the Distance

Once both locations are entered, the Range Finder will automatically calculate and display the distance between Point A and Point B in metres.

No additional input is needed.

## How It Works & Fair Play

**Where do the coordinates come from?**

Directly from the **Windows clipboard**—not from the game's memory. WARDOGS already provides coordinates through its **Mark Coordinates** map option. After the game places them in the chat input, you copy them using **Ctrl + A** and **Ctrl + C**. The Range Finder reads that copied text when you use its shortcut and calculates the distance between the two points. You can also enter coordinates manually.

**Does it interact with the game or pose an anti-cheat risk?**

The Range Finder is a standalone calculator. It **does not read, modify, or inject code into the game's memory**. It uses coordinates that the game itself makes available to players, copied through the normal Windows clipboard, and performs its calculations outside the game. This avoids the game-memory interactions commonly associated with cheats and related anti-cheat detection.

Its purpose is **accessibility and convenience**, not to reveal hidden information or provide an unfair gameplay advantage. Any player can obtain the same coordinates in-game and calculate the same straight-line distance manually; the tool simply makes that calculation quicker and easier.

**Has Bulkhead approved its use?**

Not specifically. Although the tool does not access game memory or provide information unavailable in-game, **no third-party tool can be guaranteed to be exempt from anti-cheat detection or permitted under a game's rules without confirmation from the developer**. Bulkhead's rules and any future changes to them still apply.

## Additional Information

- **New measurements:** Simply repeat the process to update either point. The distance recalculates automatically.
- **Custom shortcuts:** Change F9 or F10 in the Clipboard keybinds section and select Apply keybinds.
- **Manual entry:** Coordinates can also be pasted directly into either field, for example `x80.27, y82.27`.
- **Distance accuracy:** Results represent horizontal straight-line distance and do not account for obstacles, changes in elevation, or travel routes.

## Troubleshooting

**Nothing happens when pressing F9 or F10?**

Ensure you've copied the coordinates using Ctrl + C and that the Range Finder is running. Check the shortcut status in the application.

**Getting an invalid coordinates error?**

Make sure only the coordinates have been copied, in a supported format such as `x80.27, y82.27`.

**Not getting a distance?**

Ensure both Current position and Destination contain valid coordinates.

**Application not opening?**

Check that Python 3 and the Windows Python launcher are installed, and that both program files are stored together.
