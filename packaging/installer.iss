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
; --- Replacing files the app still has open ---------------------------------
; The build being upgraded is very likely still running when Setup reaches the
; copy step, and replacing a running executable is what produces the failure
; these two directives (and WaitForAppExecutable in [Code]) exist to avoid:
;
;   An error occurred while trying to replace the existing file:
;   DeleteFile failed; code 5. Access is denied.
;
; named on {app}\mtgo_tools.exe. Both install paths reach it. An in-app update
; (services/update_installer.py) starts this Setup and only *then* closes the
; app, and that close is not instant — it joins background threads with a 10 s
; timeout each (utils/background_worker.py) before the process can begin to
; exit. A manual install over a running app is the same situation without the
; race.
;
; CloseApplications=yes is Inno's default and is stated explicitly because the
; wait in [Code] is positioned around it. It is what makes Setup ask Windows
; Restart Manager to close the app before copying — and RM does find the app,
; but it cannot close it. A PyInstaller onefile build is two processes: the
; bootloader that unpacked the bundle into %TEMP%\_MEIxxxxxx, and the child that
; is the actual app. The bootloader has no window, so RM's graceful shutdown has
; nothing to send a close request to. Reproduced against a onefile build in a
; throwaway installer built from this script, whose /LOG reads:
;
;   RestartManager found an application using one of our files: mtgo_tools
;   RestartManager found an application using one of our files: mtgo_tools
;   Shutting down applications using our files.
;   Some applications could not be shut down.
;
; and the install then ends on an Abort/Retry/Ignore box — the same install
; failing, one dialog earlier than the DeleteFile one. It is kept on because it
; still handles every *other* holder of a file under {app} (the bundled bridge,
; a shell preview handler), and because WaitForAppExecutable() in [Code] runs
; before it: by the time RM tries, the app has normally finished exiting and
; there is nothing left to close.
;
; Deliberately not `force`: a forced close is a kill, and the app writes its
; session (window layout, panel sizes, open decks) on the way out. Losing that
; to save a few seconds on an install the user can simply retry is a bad trade.
;
; RestartApplications=no because two separate mechanisms would otherwise bring
; the app back after an update: Restart Manager restarts what it closed, and the
; /RELAUNCH [Run] entry below starts it too. That is two copies of the app, and
; the RM restart is also Setup-launches-the-app — the pattern Application
; Control refuses (#1009, #1020). The [Run] entry owns the relaunch.
;
; AppMutex is deliberately NOT used here. It aborts an install outright while
; the app is running, including a /SILENT one — which is precisely the in-app
; update path — and it only works when the *running* build creates the named
; mutex. No released build does, so it could not help any upgrade from a build
; that already shipped, which is every upgrade this fix is for.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; Finished-page wording. This replaces the "launch the app now" checkbox that
; used to live in [Run] -- see the comment there for why it is gone.
;
; Chosen over the alternatives deliberately. An InfoAfterFile would add a whole
; extra wizard page for two sentences, and a [CustomMessages] string needs
; [Code] to get onto the page at all; overriding the stock messages puts the
; instruction exactly where the user is already looking, with no new page and no
; Pascal. Inno picks FinishedLabel when Setup created a shortcut and
; FinishedLabelNoIcons when it did not, and it picks at run time, so both are
; overridden -- an override on only one of them is a finish page that silently
; reverts to the stock text under conditions you cannot see from here.
;
; Untagged (no "english." prefix), so these apply to every entry in [Languages].
; That section currently lists exactly one language, English, so there is no
; second catalogue to keep in sync today -- but if a language is ever added
; here, these two lines still cover it in English rather than going blank, and
; that is the moment to add "<lang>.FinishedLabel=" siblings. The app's own
; en-US/pt-BR catalogues under utils/i18n/ are unrelated: they translate the
; application, not Setup, which ships only what [Languages] declares.
;
; %n is Inno's newline escape and [name] expands to AppName.
FinishedLabel=Setup has finished installing [name] on your computer.%n%nTo start it, open the Start menu and choose [name] (or use the desktop shortcut, if you asked for one).%n%nSetup does not start [name] for you: on some machines Windows Application Control blocks a program that an installer launches. Opening it from the Start menu is not affected.
FinishedLabelNoIcons=Setup has finished installing [name] on your computer.%n%nTo start it, open the Start menu and choose [name].%n%nSetup does not start [name] for you: on some machines Windows Application Control blocks a program that an installer launches. Opening it from the Start menu is not affected.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable created by PyInstaller. mtgo_tools.spec is a onefile build
; (a single EXE(), no COLLECT), so this one file is the whole application — the
; recursive rule below is for everything else that the build script drops into
; dist/, not for a bundle directory.
Source: "../dist/{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Everything else the build script put in dist/. Exclude the
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
; There is deliberately no "Launch MTGO Tools" checkbox here.
;
; It used to be this entry:
;
;   Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,...}";
;       Flags: nowait postinstall skipifsilent
;
; `postinstall` is what turns a [Run] entry into that checkbox, and ticking it
; made *Setup* the process that started the app. On a machine with Windows
; Application Control active (Smart App Control on consumer Windows 11, App
; Control for Business / WDAC on managed ones) that is refused, and the install
; ends on "CreateProcess failed; code 4551 -- an Application Control policy has
; blocked this file" (issue #1009). The app is installed and fine at that point;
; the same user can open it from the Start menu immediately afterwards, which is
; the workaround #1009 reports. So the checkbox does not fail gracefully -- it
; manufactures an error dialog for an install that worked.
;
; Rather than word that error better, we stopped provoking it: the finish page
; now points at the Start Menu shortcut created in [Icons] (see the [Messages]
; overrides above). The cost is one extra click for everyone; the benefit is
; that nobody's install ends on a scary failure.
;
; RESTORE THIS ONCE THE BINARY IS CODE-SIGNED. Application Control blocks
; mtgo_tools.exe because it carries no trusted publisher signature; a signed
; build is expected to launch from Setup normally, at which point the checkbox
; is a straight usability win and should come back (together with reverting the
; FinishedLabel/FinishedLabelNoIcons overrides above). A code-signing
; certificate is being pursued through the SignPath Foundation open-source
; programme. Do not restore it before then: doing so reopens #1009.
;
; Relaunch after an in-app update. The updater downloads this installer, verifies
; its SHA256, runs it as `/SILENT /RELAUNCH`, and exits so its own files can be
; overwritten — which means nothing is left running to bring the app back. This
; entry is what brings it back.
;
; It could not be folded into the postinstall checkbox that used to sit above,
; and must not be folded into it if that checkbox is ever restored: `postinstall`
; turns a [Run] entry into a checkbox on the Finished page, and `skipifsilent`
; deliberately suppresses that page's actions under /SILENT — which is precisely
; the mode a self-update runs in. The two flags together mean "launch only when a
; human is watching", so a silent install can never launch anything through them.
; The trap is that this looks like it should work and simply does nothing.
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
;
; KNOWN, UNFIXED: this entry is still Setup calling CreateProcess on an unsigned
; mtgo_tools.exe, so on a machine with Application Control active it should be
; refused for exactly the same reason the checkbox above was — meaning an
; auto-update there leaves the app closed and it does not come back. It is left
; alone on purpose: removing it would break the update restart for everyone to
; help the few, and the obvious alternative (launching the Start Menu shortcut
; via explorer.exe, so the launch is re-parented the way the #1009 workaround is)
; cannot be verified without a machine that actually has Smart App Control on.
; Tracked in #1020. Code-signing resolves this one too.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: RelaunchRequested

[Code]
// Win32 SetEnvironmentVariableW, used by ClearInheritedBootloaderVars below.
// Declared with a string second parameter and called with '' rather than the
// documented NULL: Pascal Script has no null pointer to pass, and Windows drops
// a variable set to an empty value from the environment block anyway, which is
// exactly the "as if it was never set" this needs. Verified against the real
// bootloader rather than assumed -- an emptied-but-present variable would hit a
// different failure ("Invalid value in _PYI_PARENT_PROCESS_LEVEL").
function SetEnvironmentVariable(lpName: string; lpValue: string): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

// Remove the PyInstaller bootloader variables Setup inherited from the app that
// started it, so the app relaunched below does not inherit them in turn.
//
// The app is a PyInstaller onefile build: it runs from a directory it unpacked
// into %TEMP% (_MEIxxxxxx) and points its own child processes at that directory
// through _PYI_APPLICATION_HOME_DIR / _PYI_ARCHIVE_FILE / _PYI_PARENT_PROCESS_LEVEL,
// which is how its multiprocessing workers reuse the bundle. Those variables are
// in the environment of every process it starts -- including this Setup, launched
// by services/update_installer.py.
//
// Left alone, they are fatal here. Setup relaunches {app}\mtgo_tools.exe, that
// process inherits them, and the bootloader decides whether it is a re-executed
// child by asking whether _PYI_ARCHIVE_FILE names the executable now running.
// After an update it does -- the new build is at the same path as the old one --
// so it skips unpacking and loads Python from _PYI_APPLICATION_HOME_DIR: the old
// app's unpack directory, deleted when that app exited seconds ago. The result is
// a bootloader error box, "Failed to load Python DLL '...\_MEIxxxxxx\python3xx.dll'",
// and no app.
//
// update_installer.py now filters these before starting Setup, which fixes
// updates launched by builds carrying that fix. This does the same one step
// later, and is what makes an update launched by an *already released* build
// (1.2.0 through 1.2.7, all of which pass the variables through) survive: the
// installer that fixes the upgrade is the one being upgraded to.
//
// ssInstall, not ssPostInstall: a [Run] entry without the postinstall flag --
// the relaunch entry above -- executes at the end of the install step, which is
// *before* ssPostInstall fires. Cleaning up there runs too late to be inherited
// by anything.
procedure ClearInheritedBootloaderVars();
begin
  SetEnvironmentVariable('_PYI_APPLICATION_HOME_DIR', '');
  SetEnvironmentVariable('_PYI_ARCHIVE_FILE', '');
  SetEnvironmentVariable('_PYI_PARENT_PROCESS_LEVEL', '');
  SetEnvironmentVariable('_PYI_SPLASH_IPC', '');
  // The pre-6.0 spelling, cleared so a rollback of the pinned PyInstaller
  // cannot quietly reopen this.
  SetEnvironmentVariable('_MEIPASS2', '');
end;

// Win32 CreateFileW/CloseHandle, used by AppExecutableInUse below.
//
// Declared returning Integer rather than an unsigned handle type on purpose:
// Setup is a 32-bit process, every handle it is handed fits comfortably in a
// positive Integer, and INVALID_HANDLE_VALUE is then simply -1 -- which avoids
// having to compare a Pascal Script value against $FFFFFFFF and get the
// signedness right. The pointer parameter (lpSecurityAttributes) is passed as 0
// for the same reason '' is passed to SetEnvironmentVariableW above: Pascal
// Script has no NULL, and 0 is what NULL is.
function CreateFileW(lpFileName: string; dwDesiredAccess, dwShareMode,
  lpSecurityAttributes, dwCreationDisposition, dwFlagsAndAttributes,
  hTemplateFile: Cardinal): Integer;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(hObject: Integer): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

const
  AppExeWriteAccess = $40000000;      // GENERIC_WRITE
  AppExeOpenExisting = 3;             // OPEN_EXISTING
  AppExeNormalAttributes = $80;       // FILE_ATTRIBUTE_NORMAL
  AppExeInvalidHandle = -1;           // INVALID_HANDLE_VALUE
  // How long WaitForAppExecutable will wait, and how often it re-asks. The
  // timeout is generous because the app's own shutdown can be: it joins
  // background threads with a 10 s timeout each and the onefile bootloader then
  // has a ~175 MB _MEIxxxxxx directory to delete before the last process holding
  // the executable goes away. It is still bounded, because waiting forever on a
  // user who left the app open would be a worse bug than the one being fixed.
  AppExitTimeoutMs = 30000;
  AppExitPollMs = 200;

// True when {app}\mtgo_tools.exe cannot be opened for writing.
//
// That is the same question Setup is about to ask when it replaces the file,
// asked cheaply and without the answer becoming a dialog: a running executable
// is mapped as an image, and Windows refuses both a write open and the delete
// that Setup's replace does first. That delete failing with ERROR_ACCESS_DENIED
// (5) is the exact error this mechanism exists to prevent.
//
// Asking the file rather than looking for a process is deliberate. It needs no
// cooperation from the build being replaced -- no mutex, no window class, no
// PID handed over on the command line -- so it works when upgrading from any
// already-released build, which is the only kind of upgrade there is. It also
// covers every holder of the file at once: the PyInstaller onefile bootloader
// runs as two processes (the parent that unpacked the bundle and the child that
// is the app), and a multiprocessing "spawn" worker is a third copy of the same
// executable. "The window is gone" does not mean "the file is free".
//
// A missing file is not in use: that is a first install, and there is nothing to
// wait for.
function AppExecutableInUse(): Boolean;
var
  Path: string;
  Handle: Integer;
begin
  Path := ExpandConstant('{app}\{#MyAppExeName}');
  if not FileExists(Path) then
  begin
    Result := False;
    Exit;
  end;
  Handle := CreateFileW(Path, AppExeWriteAccess, 0, 0, AppExeOpenExisting,
    AppExeNormalAttributes, 0);
  Result := Handle = AppExeInvalidHandle;
  if not Result then
    CloseHandle(Handle);
end;

// Give a still-running MTGO Tools a bounded chance to exit before Setup starts
// replacing its files.
//
// Called from CurStepChanged(ssInstall), and the position is load-bearing.
// Setup's install step runs in this order, observed in a /LOG from a throwaway
// installer built from this script:
//
//   Calling RestartManager's RmGetList.          <- in-use *detection*
//   ...
//   Starting the installation process.           <- ssInstall fires here
//   Shutting down applications using our files.  <- RM's shutdown *attempt*
//   ... first file copied ...
//
// ssInstall is therefore the one hook that sits after Setup knows which files
// are in use and before it does anything about them. Waiting here lets the app
// finish the exit it is already performing, so RM's attempt finds nothing left
// to close and the copy that follows cannot fail on it.
//
// Both obvious alternatives are worse. PrepareToInstall runs earlier still and
// is documented as running before the in-use check at all. A BeforeInstall:
// function on the mtgo_tools.exe [Files] entry runs *after* RM's shutdown
// attempt -- and that attempt is exactly where an install with the app still
// running already dies ("Some applications could not be shut down"), so a wait
// there would never be reached.
//
// It does not abort, and does not prompt. If the wait times out, Setup carries
// on and the user sees exactly what they see today -- Inno's own
// retry/ignore/abort dialog on the file it could not replace. This can only
// remove failures, never add one.
//
// The wait is a plain Sleep loop, so Setup's window does not pump messages while
// it runs and Windows may grey it out if the wait is long. That is accepted: the
// expected wait is a second or two (the app is already exiting), and a briefly
// unresponsive progress window is a far better outcome than a half-replaced
// install.
procedure WaitForAppExecutable();
var
  Waited: Integer;
begin
  if not AppExecutableInUse() then
    Exit;
  Log('MTGO Tools is still holding ' + ExpandConstant('{app}\{#MyAppExeName}') +
    '; waiting for it to exit');
  if WizardForm <> nil then
    WizardForm.StatusLabel.Caption := 'Waiting for MTGO Tools to finish closing...';
  Waited := 0;
  while (Waited < AppExitTimeoutMs) and AppExecutableInUse() do
  begin
    Sleep(AppExitPollMs);
    Waited := Waited + AppExitPollMs;
  end;
  if AppExecutableInUse() then
    Log('MTGO Tools still holds its executable after ' + IntToStr(Waited) +
      ' ms; continuing and letting Setup report any file it cannot replace')
  else
    Log('MTGO Tools released its executable after ' + IntToStr(Waited) + ' ms');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    ClearInheritedBootloaderVars();
    WaitForAppExecutable();
  end;
end;

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
