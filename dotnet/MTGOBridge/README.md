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
MTGOBridge.exe history      # match history snapshot only
MTGOBridge.exe all          # both snapshots in one run
MTGOBridge.exe watch        # stream challenge-timer snapshots until stopped
MTGOBridge.exe serve        # long-lived request/response mode (see below)
MTGOBridge.exe ping         # liveness check; never touches MTGOSDK
```

Running without arguments exits immediately.

Each invocation prints a JSON object containing timing metrics; the full payload is kept in memory for downstream use by the Python side of the project.

## 5. `serve` mode (long-lived)

Every one-shot invocation pays ~0.8s of .NET startup plus ~3.1s of MTGOSDK
`RemoteClient` attach before it does any work, and several bridge processes
attached at once degrade per-call latency roughly 8x because MTGOSDK marshals
all reads onto MTGO's UI thread. `serve` keeps one process — and one request
queue — alive instead, so the attach is paid once and nothing contends.

It reads one JSON request per line on stdin and writes one JSON message per line
on stdout:

```jsonc
// -> requests
{"id":"7","command":"collection","args":[]}
{"id":"8","command":"trade","args":["status"]}
{"id":"9","command":"watch","args":["start","500"]}   // then ["stop"]
// <- responses (payload is byte-identical to the one-shot CLI output)
{"id":"7","ok":true,"payload":{ /* ... */ }}
{"id":"8","ok":false,"error":"..."}
// <- unsolicited events
{"event":"ready","payload":{"protocol":1,"pid":1234}}
{"event":"watch","payload":{ /* WatchSnapshot */ }}
{"event":"disconnected","payload":{"reason":"MTGO process exited"}}
```

`command` accepts every one-shot mode name. The `ready` banner is printed before
MTGOSDK is touched, so a client can tell a build that supports `serve` from one
that does not (the latter exits immediately). Closing stdin shuts the process
down; it also exits on its own once the MTGO process it attached to is gone, so
the client can respawn against a restarted client.

The Python side drives this from `services/mtgo_bridge_service/session.py`.
Setting `MTGO_BRIDGE_NO_SESSION=1` forces it back to one process per command.

## Troubleshooting

### MTGOSDK package not found
Ensure you're using .NET 9.0 SDK and have internet access to NuGet.org.

### Build errors
Make sure MTGO is installed on your system. The MTGOSDK requires MTGO to be present.

### Runtime errors
MTGO must be running when you execute the bridge for collection or history exports.

---

For more detail on MTGOSDK usage and API surface, refer to the upstream documentation:
<https://github.com/videre-project/MTGOSDK/tree/main/docs>
