# Trackmania 2020 native C++ bridge — installation and integration status

Updated October 21, 2026. All research on H:\Projects\Trackmania2020-RE.
Trackmania.exe Steam game installed on D:\SteamLibrary\steamapps\common\Trackmania.

## Ubisoft Connect installation: SUCCESS

- Official publisher CDN: https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe
- Local downloaded installer: H:\Projects\Trackmania2020-RE\references\ubisoft-connect-official\UbisoftConnectInstaller.exe
- Downloaded installer: 264,202,144 bytes, SHA-256 3CEC13ADB297DAF861528CA59C94467D9AEE4B43B0089EBC211CF5DE16618503.
- Installer WinVerifyTrust Authenticode signature: Valid, Ubisoft Entertainment Inc.
- Installed launcher: D:\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe
- Windows registry reports version 174.2.13389, location on D:, launcher signed by Ubisoft. Installed directory initially ~462MB.
- Game default install location also on D:. Ubisoft settings and login app-data may be written to C: as user explicitly approved.
- Launcher was started normally; its UI displays Ubisoft account SIGN IN.
- **Ubisoft account sign-in requires the user.** No credentials, browser sessions, tokens, or second-factor authentication were accessed.
- Steam appmanifest_2225070.acf exists for installed Trackmania. A normal Steam launch can be tested after authentication, using:
  & 'H:\Projects\Trackmania2020-RE\scripts\launch-trackmania-after-login.ps1'
- The authenticated Trackmania local race has NOT yet run successfully. A read-only process probe succeeded earlier when the game displayed the "Ubisoft Connect is not installed" error (before installation), but that was not a vehicle session.

## C++ SDK, no Openplanet dependency

- C++20 CMake SDK version 0.3 installs native bridge DLL:
  H:\Projects\Trackmania2020-RE\dist\sdk-windows-x64\bin\libtm2020_bridge.dll.
- C ABI version 2 accepts position, velocity, steering context, yaw, speed, lateral speed, four wheel ground material IDs, ground-contact flag, game tick and caller-supplied offline/local assertion.
- Separate C++ host uses LoadLibrary/GetProcAddress; returns advisory steer/gas/brake. Rejects invalid, stale or caller-asserted nonlocal observations. The caller-supplied offline assertion is NOT independently verified by the SDK.
- Extensive test now streams ALL 24 public replay datasets (11,050 measured in-race vehicle snapshots) through DLL in a separate C++ host, 0 API errors, over one million output predictions/sec on the PC.
- There is NO DLL injection into the Trackmania process yet; no protected online game code/hook/DRM/anti-cheat interference. No control input is actually sent to the game.
- Offline static PE recon on installed Trackmania.exe 2026.2.2.1751: 11 sections, 321 relevant named string occurrences and candidate references; addresses are NOT validated car fields.
- Native read-only process probe can read module header and expected strings once game launches normally. No actual vehicle owner memory pointers, physics fields, game-engine tick callbacks or control callsites are confirmed.

## Fidelity barriers

- No complete Stadium collision/geometry reconstruction; current custom-object mesh coverage is very partial.
- Native experimental 100Hz sandbox deliberately uses flat-plane toy dynamics, fails differential Trackmania trajectory tests.
- Observed vehicle states in public replays appear every 50ms; event stream can have 10ms input ticks. A tick-perfect 100Hz state feed is not ready.
- Native supervised BC policy remains weaker than a neutral steering baseline on held-out maps, and route plan depends on a known demonstration replay.
- High-fidelity headless Trackmania RL and a reliable autonomous in-game bot are NOT ready.

## Reproducible commands

Test everything, WITHOUT requiring Openplanet:
  & 'H:\Projects\Trackmania2020-RE\scripts\run-framework-tests.ps1'

Status:
  & 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'

After Ubisoft account sign-in on this PC:
  & 'H:\Projects\Trackmania2020-RE\scripts\launch-trackmania-after-login.ps1'

The normal game launch test ONLY starts Steam app 2225070 and runs a read-only process probe; it does not inject the bridge or drive a multiplayer game.

The earlier attempt to install or use Openplanet is no longer part of the native bot runtime or the default regression suite.
