; Inno Setup Script for MTGO Tools
; This script creates a Windows installer with license agreement, custom install directory, and shortcuts

#define MyAppName "MTGO Tools"
; Single source of truth for the version is the repo-root VERSION file. It is
; owned by the semver automation (scripts/next_version.py + the Versioning CI
; workflow), which bumps it from conventional-commit messages. Read it here at
; compile time so the installer and its output filename always match.
#define VerFile FileOpen(AddBackslash(SourcePath) + "..\VERSION")
#define MyAppVersion Trim(FileRead(VerFile))
#expr FileClose(VerFile)
#if MyAppVersion == ""
  #error VERSION file is missing or empty (expected at repo root)
#endif
#define MyAppPublisher "MTGO Metagame Crawler Contributors"
#define MyAppURL "https://github.com/Pedrogush/MTGO_Tools"
#define MyAppExeName "mtgo_tools.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId value in installers for other applications.
AppId={{8F9A2D3B-1C4E-5F6A-7B8C-9D0E1F2A3B4C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install: no administrator privileges required. With PrivilegesRequired=lowest
; the {autopf} constant resolves to the user's local Programs directory
; (%LOCALAPPDATA%\Programs), and the app writes all of its data under
; %LOCALAPPDATA%\{#MyAppName} (see utils/constants/paths.py), so nothing needs
; to be written to a location that requires elevation.
PrivilegesRequired=lowest
OutputDir=../dist/installer
OutputBaseFilename=MTGOTools_Setup_v{#MyAppVersion}
; Icon for the installer executable itself.
SetupIconFile=../assets/icons/hammer.ico
; Icon shown in Apps & Features / Add-Remove Programs (uses the app's own icon).
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; License file
LicenseFile=../LICENSE
; Require Windows 10 or later (matches .NET 9 requirement)
MinVersion=10.0.17763
; Only support x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable created by PyInstaller
Source: "../dist/{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; All other files from the PyInstaller bundle (for a onedir build). Exclude the
; installer output dir, which lives at dist/installer — without this the
; installer bundles a copy of its own output directory (and any previously built
; setup .exe) into {app}\installer.
;
; This recursive rule is ALSO how the bundled bulk-data seed ships: build_installer.ps1
; writes dist/seed/bulk_data.json.gz (Scryfall's default_cards, gzipped ~130 MB),
; so it installs to {app}\seed\bulk_data.json.gz. On first run the app decompresses
; it into the image cache (services/image_service/seed.py) so a fresh install starts
; warm instead of racing a cold download. If the seed step was skipped, dist/seed
; simply doesn't exist and nothing is shipped — the app falls back to downloading.
Source: "../dist/*"; DestDir: "{app}"; Excludes: "installer,installer\*"; Flags: ignoreversion recursesubdirs createallsubdirs
; MTGO integration bridge — a self-contained .NET publish that bundles its own
; runtime. Built by build_installer.ps1 (dotnet publish -r win-x64
; --self-contained) and shipped here so MTGO integration works out of the box:
; no install-time download and no separate .NET runtime requirement on the user's
; machine. The app resolves it at {app}\mtgo_integration\MTGOBridge.exe
; (see services/mtgo_bridge_service/discovery.py). Intentionally NOT wrapped in a
; #if DirExists guard: if the bridge was not built, ISCC must fail rather than
; silently ship an installer without MTGO integration.
Source: "../dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/publish/*"; DestDir: "{app}\mtgo_integration"; Flags: ignoreversion recursesubdirs createallsubdirs
; Vendor data directories (if they exist)
; NOTE: vendor/mtgosdk (C# SDK sources) is intentionally excluded; the compiled,
; self-contained bridge is bundled above and needs nothing else at runtime.
#if DirExists('../vendor/mtgo_format_data')
Source: "../vendor/mtgo_format_data/*"; DestDir: "{app}/vendor/mtgo_format_data"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
#if DirExists('../vendor/mtgo_archetype_parser')
Source: "../vendor/mtgo_archetype_parser/*"; DestDir: "{app}/vendor/mtgo_archetype_parser"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
; README and LICENSE
Source: "../README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "../LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Runtime data (config/cache/logs/data) lives under %LOCALAPPDATA%\{#MyAppName},
; not under {app}, so the app creates those directories at runtime. The bundled
; MTGO bridge ships into {app}\mtgo_integration via the [Files] section above, so
; nothing needs to be pre-created here.

[UninstallDelete]
; The bundled bridge files in {app}\mtgo_integration are recorded by Setup and
; removed automatically on uninstall. This entry additionally sweeps anything the
; bridge writes next to itself at runtime, so the folder is left empty and removed
; rather than orphaned.
Type: filesandordirs; Name: "{app}\mtgo_integration"
; Regenerable per-user data: caches, logs, and downloaded card data. User
; settings (%LOCALAPPDATA%\{#MyAppName}\config) and saved decks
; (%USERPROFILE%\Documents\mtgo_decks) are intentionally preserved so a
; reinstall keeps them.
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\cache"
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\logs"
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\data"

[Icons]
; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\README"; Filename: "{app}\README.md"
; Desktop shortcut (optional, based on task selection)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch the application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Relaunch after an in-app update. The updater downloads this installer, verifies
; its SHA256, runs it as `/SILENT /RELAUNCH`, and exits so its own files can be
; overwritten — which means nothing is left running to bring the app back. This
; entry is what brings it back.
;
; It cannot be folded into the entry above: `postinstall` turns a [Run] entry into
; a checkbox on the Finished page, and `skipifsilent` deliberately suppresses that
; page's actions under /SILENT — which is precisely the mode a self-update runs in.
; The two flags together mean "launch only when a human is watching", so a silent
; install can never launch anything through them. The trap is that this looks like
; it should work and simply does nothing.
;
; So this is a plain [Run] entry (no postinstall): it executes at the end of the
; install regardless of silence, and a Check: function is what makes it conditional
; instead. Without /RELAUNCH the Check returns False and the entry is skipped, so a
; normal interactive install is byte-for-byte the experience it was before.
;
; nowait is load-bearing rather than cosmetic: Setup waits for a [Run] entry it
; started unless told not to, and the app runs for hours. Without it Setup would
; stay alive for the entire session — a stray process holding an install lock,
; long after the update it performed was finished.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: RelaunchRequested

[Code]
// True only when Setup was started with a /RELAUNCH switch (see [Run] above).
//
// Inno has no built-in "was this bare flag passed?" helper. The closest thing is
// the {param:Name} constant, which only reads /Name=Value pairs and so cannot
// answer the question -- hence walking the parameter list by hand.
//
// Deliberately // line comments rather than a { ... } block: brace comments do
// not nest, so the constant named above would close the comment early and the
// rest of it would be compiled as code.
//
// The scan starts at 0, not 1. ParamStr(0) is conventionally Setup's own
// executable path (Delphi semantics, which Inno mirrors) and so would never
// match, but this file cannot be compiled on the Linux side of this project and
// the failure mode if that assumption is ever wrong is the worst kind: the
// switch is silently ignored and the app simply never comes back after an
// update. Reading one extra parameter costs nothing and removes the assumption.
//
// CompareText is case-insensitive, matching how Windows and Inno's own switches
// (/SILENT, /DIR=...) are treated -- a caller writing /relaunch means the same
// thing. Setup ignores switches it does not recognise, so /RELAUNCH reaches here
// without having to be declared anywhere else.
function RelaunchRequested(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to ParamCount do
  begin
    if CompareText(ParamStr(I), '/RELAUNCH') = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;
