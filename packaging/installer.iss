; Inno Setup Script for MTGO Metagame Deck Builder
; This script creates a Windows installer with license agreement, custom install directory, and shortcuts

#define MyAppName "MTGO Metagame Deck Builder"
#define MyAppVersion "0.2"
#define MyAppPublisher "MTGO Metagame Crawler Contributors"
#define MyAppURL "https://github.com/yourusername/magic_online_metagame_crawler"
#define MyAppExeName "magic_online_metagame_crawler.exe"

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
; Uncomment the following line to run in non administrative install mode (install for current user only.)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=../dist/installer
OutputBaseFilename=MTGOMetagameBuilder_Setup_v{#MyAppVersion}
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
; All other files from PyInstaller bundle
Source: "../dist/*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Vendor data directories (if they exist)
; NOTE: vendor/mtgosdk is intentionally excluded — the bridge is downloaded at install time.
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
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\config"; Permissions: users-modify
Name: "{app}\cache"; Permissions: users-modify
Name: "{app}\decks"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\mtgo_integration"; Permissions: users-modify

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

[Code]
// ---------------------------------------------------------------------------
// Bridge download constants
// ---------------------------------------------------------------------------
const
  BRIDGE_RELEASE_URL   = 'https://github.com/Pedrogush/MTGOBridge/releases/download/v1.0.0/MTGOBridge-v1.0.0.zip';
  BRIDGE_MANUAL_URL    = 'https://github.com/Pedrogush/MTGOBridge/releases/latest';
  BRIDGE_ZIP_FILENAME  = 'MTGOBridge-v1.0.0.zip';
  DOTNET9_WINGET_ID    = 'Microsoft.DotNet.Runtime.9';

// ---------------------------------------------------------------------------
// .NET 9 detection
// ---------------------------------------------------------------------------
function IsDotNet9Installed: Boolean;
var
  ResultCode: Integer;
begin
  // dotnet --list-runtimes exits 0 even when no matching runtime is found;
  // we use a simple presence check via "dotnet" availability and version list.
  Result := Exec('powershell.exe',
    '-NoProfile -NonInteractive -Command "dotnet --list-runtimes 2>$null | '
    + 'Select-String ''Microsoft.NETCore.App 9\.''"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

// ---------------------------------------------------------------------------
// PowerShell-based HTTP download helper
// ---------------------------------------------------------------------------
function DownloadFilePS(const Url, Dest: String): Boolean;
var
  ResultCode: Integer;
  Script: String;
begin
  Script := Format(
    'Invoke-WebRequest -Uri ''%s'' -OutFile ''%s'' -UseBasicParsing', [Url, Dest]);
  Result := Exec('powershell.exe',
    '-NoProfile -NonInteractive -Command "' + Script + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

// ---------------------------------------------------------------------------
// PowerShell-based zip extraction helper
// ---------------------------------------------------------------------------
function ExtractZipPS(const ZipPath, DestDir: String): Boolean;
var
  ResultCode: Integer;
  Script: String;
begin
  Script := Format(
    'Expand-Archive -Path ''%s'' -DestinationPath ''%s'' -Force', [ZipPath, DestDir]);
  Result := Exec('powershell.exe',
    '-NoProfile -NonInteractive -Command "' + Script + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

// ---------------------------------------------------------------------------
// Bridge download + extraction
// ---------------------------------------------------------------------------
procedure DownloadBridge;
var
  ZipPath, IntegrationDir: String;
  DownloadOk, ExtractOk: Boolean;
begin
  IntegrationDir := ExpandConstant('{app}\mtgo_integration');
  ZipPath        := ExpandConstant('{tmp}\') + BRIDGE_ZIP_FILENAME;

  Log('Downloading MTGOBridge from ' + BRIDGE_RELEASE_URL);
  DownloadOk := DownloadFilePS(BRIDGE_RELEASE_URL, ZipPath);

  if not DownloadOk then
  begin
    MsgBox(
      'MTGO integration could not be downloaded automatically.' + #13#10 +
      'You can install it manually later from:' + #13#10 +
      BRIDGE_MANUAL_URL + #13#10#13#10 +
      'The main application will work without it.' ,
      mbInformation, MB_OK);
    Log('Bridge download failed — MTGO integration will be unavailable.');
    Exit;
  end;

  Log('Extracting MTGOBridge to ' + IntegrationDir);
  ExtractOk := ExtractZipPS(ZipPath, IntegrationDir);

  if not ExtractOk then
  begin
    MsgBox(
      'MTGOBridge was downloaded but could not be extracted.' + #13#10 +
      'You can install it manually from:' + #13#10 +
      BRIDGE_MANUAL_URL,
      mbInformation, MB_OK);
    Log('Bridge extraction failed — MTGO integration will be unavailable.');
  end;
end;

// ---------------------------------------------------------------------------
// .NET 9 detection and prompt
// ---------------------------------------------------------------------------
procedure CheckAndPromptDotNet9;
var
  ResultCode: Integer;
begin
  if not IsDotNet9Installed then
  begin
    if MsgBox(
      'MTGO integration requires the .NET 9 Runtime, which was not detected.' + #13#10 +
      'Would you like to install it now via winget?',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('winget.exe',
        'install --id ' + DOTNET9_WINGET_ID + ' --silent --accept-source-agreements'
        + ' --accept-package-agreements',
        '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
      if ResultCode <> 0 then
        MsgBox(
          'winget installation may not have completed.' + #13#10 +
          'Please install .NET 9 Runtime manually from https://dotnet.microsoft.com/download/dotnet/9.0',
          mbInformation, MB_OK);
    end;
  end;
end;

// ---------------------------------------------------------------------------
// Post-install step
// ---------------------------------------------------------------------------
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CheckAndPromptDotNet9;
    DownloadBridge;
  end;
end;
