# MTGO Bridge Setup

This directory contains a lightweight .NET bridge that pulls data from the MTGOSDK and feeds it to the Python tooling. Follow the steps below to install the required tooling, add the MTGOSDK package, and build the bridge executable.

## 1. Install the .NET SDK (Windows)

1. Download and install [.NET 9.0 SDK or newer](https://dotnet.microsoft.com/download/dotnet/9.0).
2. Open **Windows PowerShell** and verify the installation:
   ```powershell
   dotnet --info
   ```
   You should see the installed SDK listed in the output.

> **Tip:** If you already have Visual Studio 2022 (v17.x) or later installed with .NET tooling, the SDK may already be available.

## 2. Restore dependencies and add MTGOSDK

From the repository root:

```powershell
cd dotnet/MTGOBridge
dotnet restore
dotnet add package MTGOSDK
```

This pulls MTGOSDK from NuGet. If you need to target a specific release or local feed, pass `--version` or configure `NuGet.Config` accordingly.

## 3. Build and publish the bridge

### Build (fast iteration)
```powershell
dotnet build MTGOBridge.csproj
```

### Publish Windows executable
```powershell
dotnet publish MTGOBridge.csproj -c Release -r win-x64 --self-contained false
```

The packaged binary will be located in:
```
dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe
```

## 4. Run the bridge

The executable accepts a mode argument:

```powershell
MTGOBridge.exe collection   # collection snapshot only
MTGOBridge.exe currency      # event tickets / play points / treasure chests
MTGOBridge.exe all          # collection + currency in one run
MTGOBridge.exe username     # logged-in MTGO account name
MTGOBridge.exe logfiles     # GameLog file paths
MTGOBridge.exe trade status # active trade snapshot
MTGOBridge.exe watch        # streaming challenge timers + currency
```

Running without arguments exits immediately.

Each invocation prints a JSON object containing timing metrics; the full payload is kept in memory for downstream use by the Python side of the project.

## Troubleshooting

### MTGOSDK package not found
Ensure you're using .NET 9.0 SDK and have internet access to NuGet.org.

### Build errors
Make sure MTGO is installed on your system. The MTGOSDK requires MTGO to be present.

### Runtime errors
MTGO must be running when you execute the bridge for collection or currency exports.

---

For more detail on MTGOSDK usage and API surface, refer to the upstream documentation:
<https://github.com/videre-project/MTGOSDK/tree/main/docs>
