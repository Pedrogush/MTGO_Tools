using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using MTGOSDK.API;
using MTGOSDK.API.Collection;
using MTGOSDK.API.Play;
using MTGOSDK.API.Play.Games;
using MTGOSDK.API.Play.Tournaments;
using MTGOSDK.API.Play.History;
using MTGOSDK.API.Play.Leagues;
using MTGOSDK.API.Users;
using MTGOSDK.API.Trade;
using MTGOSDK.API.Trade.Enums;
// dotnet publish dotnet/MTGOBridge/MTGOBridge.csproj -c Release -r win-x64 --self-contained false
var mode = ParseMode(args);
if (mode == ExecutionMode.None)
{
    return;
}

var jsonOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = false,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
};

if (mode == ExecutionMode.Watch)
{
    RunWatchLoopAsync(jsonOptions).GetAwaiter().GetResult();
    return;
}

if (mode == ExecutionMode.Serve)
{
    RunServeLoop(jsonOptions);
    return;
}

// Observed timings with ~2,070 unique cards (2026-09-18): collectionMs ≈ 1_420 of
// actual IPC, inside a ~9_000 ms process because ~7_200 ms of every invocation is
// .NET startup plus the RemoteClient attach. The collection read itself is only 7
// IPC calls — GetFrozenCollection returns Id/Name/Quantity locally. `serve` mode
// amortises that startup+attach across every request instead of paying it once
// per command.
Console.WriteLine(JsonSerializer.Serialize(BuildPayload(mode, args), jsonOptions));

// Builds the payload a single CLI invocation prints. `serve` mode calls the same
// function per request, so a request over the long-lived pipe and a one-shot
// `MTGOBridge.exe <mode>` return byte-identical JSON and the Python side can
// parse both with one code path.
static object BuildPayload(ExecutionMode mode, string[] args)
{
    switch (mode)
    {
        case ExecutionMode.Ping:
            return new PingSnapshot(true, DateTimeOffset.UtcNow);
        case ExecutionMode.LogFiles:
            return GetLogFilesSnapshot();
        case ExecutionMode.Username:
            return GetUsernameSnapshot();
        case ExecutionMode.Trade:
            return ParseTradeCommand(args) == TradeCommand.Accept
                ? AcceptTradeSnapshot()
                : (object)GetTradeStatusSnapshot();
    }

    var timings = new Dictionary<string, long>(StringComparer.OrdinalIgnoreCase);
    var totalStopwatch = Stopwatch.StartNew();

    CollectionSnapshot? collectionSnapshot = null;
    CurrencySnapshot? currencySnapshot = null;

    if (mode is ExecutionMode.Collection or ExecutionMode.All)
    {
        collectionSnapshot = Measure("collectionMs", GetCollectionSnapshot, timings);
    }

    if (mode is ExecutionMode.Currency or ExecutionMode.All)
    {
        currencySnapshot = Measure("currencyMs", GetCurrencySnapshot, timings);
    }

    totalStopwatch.Stop();
    timings["totalMs"] = totalStopwatch.ElapsedMilliseconds;

    return new BridgePayload(
        DateTimeOffset.UtcNow,
        mode.ToString(),
        collectionSnapshot,
        currencySnapshot,
        timings
    );
}

static T Measure<T>(string key, Func<T> factory, IDictionary<string, long> timings)
{
    var sw = Stopwatch.StartNew();
    try
    {
        return factory();
    }
    finally
    {
        sw.Stop();
        timings[key] = sw.ElapsedMilliseconds;
    }
}

static UsernameSnapshot GetUsernameSnapshot()
{
    // Cheapest possible discriminator: without this, "MTGO isn't running" and
    // "MTGO is running but the username lookup broke" both surfaced as the same
    // opaque TargetInvocationException, which is what made this failure so hard
    // to read from the app log.
    if (Process.GetProcessesByName("MTGO").Length == 0)
    {
        return new UsernameSnapshot(null, "MTGO client is not running");
    }

    var errors = new List<string>();

    // Strategy 1: Client.CurrentUser.
    // Each strategy gets its own try/catch. Previously a single try wrapped all
    // three, so strategy 1 throwing made 2 and 3 unreachable.
    try
    {
        var clientType = Type.GetType("MTGOSDK.API.Client, MTGOSDK");
        if (clientType != null)
        {
            // CurrentUser is static on MTGOSDK 0.8.5 but an instance property on
            // 1.6.x (reached via the static Client.Current singleton). Probe both
            // so an SDK bump doesn't silently turn this into a no-op.
            var prop = clientType.GetProperty("CurrentUser", BindingFlags.Public | BindingFlags.Static)
                    ?? clientType.GetProperty("CurrentUser", BindingFlags.Public | BindingFlags.Instance);
            if (prop is null)
            {
                errors.Add("Client.CurrentUser not found");
            }
            else
            {
                object? target = prop.GetGetMethod()?.IsStatic == false
                    ? clientType.GetProperty("Current", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
                    : null;
                var currentUser = prop.GetValue(target);
                var name = SafeGet(currentUser, "Name", string.Empty);
                if (!string.IsNullOrWhiteSpace(name))
                {
                    return new UsernameSnapshot(name, null);
                }
                errors.Add("Client.CurrentUser returned no name");
            }
        }
        else
        {
            errors.Add("MTGOSDK.API.Client type not found");
        }
    }
    catch (Exception ex)
    {
        errors.Add("Client.CurrentUser: " + Describe(ex));
    }

    // Strategy 2: fall back to the collection's name, which MTGO sets to the
    // account name. (An earlier UserManager.CurrentUser strategy lived here; that
    // property exists on neither 0.8.5 nor 1.6.6, so it could never fire.)
    try
    {
        var collectionName = CollectionManager.Collection?.Name;
        if (!string.IsNullOrWhiteSpace(collectionName) && collectionName != "Collection")
        {
            return new UsernameSnapshot(collectionName, null);
        }
        errors.Add("Collection.Name was not a username");
    }
    catch (Exception ex)
    {
        errors.Add("Collection.Name: " + Describe(ex));
    }

    return new UsernameSnapshot(null, string.Join("; ", errors));
}

// Reflection wraps whatever a getter threw in TargetInvocationException, and an
// SDK attach failure wraps again in TypeInitializationException. Reporting
// ex.Message alone yielded the useless "Exception has been thrown by the target
// of an invocation."; GetBaseException walks past both to the real cause.
static string Describe(Exception ex)
{
    var baseEx = ex.GetBaseException();
    return $"{baseEx.GetType().Name}: {baseEx.Message}";
}

static LogFilesSnapshot GetLogFilesSnapshot()
{
    try
    {
        // GetGameHistoryFiles([optional] System.String username, [optional] System.Boolean filterFiles) -> System.String[]
        var files = HistoryManager.GetGameHistoryFiles(filterFiles: true);

        if (files == null)
        {
            return new LogFilesSnapshot(
                Array.Empty<string>(),
                "GetGameHistoryFiles returned null"
            );
        }

        return new LogFilesSnapshot(files, null);
    }
    catch (Exception ex)
    {
        return new LogFilesSnapshot(
            Array.Empty<string>(),
            ex.Message
        );
    }
}

static CollectionSnapshot GetCollectionSnapshot()
{
    try
    {
        var collection = CollectionManager.Collection;
        var frozen = collection.GetFrozenCollection ?? Array.Empty<CardQuantityPair>();
        var items = frozen
            .Select(card => new CollectionCard(card.Id, card.Name, card.Quantity))
            .ToList();

        return new CollectionSnapshot(
            collection.Id,
            string.IsNullOrWhiteSpace(collection.Name) ? "Collection" : collection.Name,
            collection.ItemCount,
            collection.MaxItems,
            items,
            null
        );
    }
    catch (Exception ex)
    {
        return new CollectionSnapshot(
            0,
            null,
            0,
            0,
            Array.Empty<CollectionCard>(),
            ex.Message
        );
    }
}

static CurrencySnapshot GetCurrencySnapshot()
{
    try
    {
        var collection = CollectionManager.Collection;
        if (collection is null)
        {
            return new CurrencySnapshot(null, null, null, "Collection manager returned null");
        }

        var frozen = collection.GetFrozenCollection ?? Array.Empty<CardQuantityPair>();
        var ticketTotal = 0;
        var pointTotal = 0;
        var chestTotal = 0;
        var hasTickets = false;
        var hasPoints = false;
        var hasChests = false;

        foreach (var entry in frozen)
        {
            if (entry is null)
            {
                continue;
            }

            if (IsEventTicket(entry))
            {
                ticketTotal += entry.Quantity;
                hasTickets = true;
                continue;
            }

            if (IsPlayPoints(entry))
            {
                pointTotal += entry.Quantity;
                hasPoints = true;
                continue;
            }

            if (IsTreasureChest(entry))
            {
                chestTotal += entry.Quantity;
                hasChests = true;
            }
        }

        return new CurrencySnapshot(
            hasTickets ? ticketTotal : null,
            hasPoints ? pointTotal : null,
            hasChests ? chestTotal : null,
            null
        );
    }
    catch (Exception ex)
    {
        return new CurrencySnapshot(null, null, null, ex.Message);
    }
}

static T SafeGet<T>(object? target, string propertyName, T defaultValue = default!)
{
    if (target is null)
    {
        return defaultValue;
    }

    try
    {
        var value = target.GetType().GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(target);
        if (value is null)
        {
            return defaultValue;
        }

        if (value is T typed)
        {
            return typed;
        }

        return (T)Convert.ChangeType(value, typeof(T));
    }
    catch
    {
        return defaultValue;
    }
}

static async Task RunWatchLoopAsync(
    JsonSerializerOptions options,
    TimeSpan? timerInterval = null,
    TimeSpan? currencyInterval = null)
{
    // The challenge-timer read is cheap and needs second-level freshness; the
    // currency read takes one GetFrozenCollection round trip (~0.9-1.3s) and
    // changes slowly — leagues run well over an hour — so the two are split into
    // independent loops at very different cadences instead of one combined tick.
    timerInterval ??= TimeSpan.FromMilliseconds(500);
    currencyInterval ??= TimeSpan.FromMinutes(10);
    Console.OutputEncoding = Encoding.UTF8;

    using var cts = new CancellationTokenSource();
    Console.CancelKeyPress += (_, args) =>
    {
        args.Cancel = true;
        cts.Cancel();
    };

    // The SDK transport is concurrency-safe, but reads are marshalled onto MTGO's
    // UI thread server-side, so a concurrent currency scan delays timer reads
    // anyway. The lock keeps the timer loop responsive — it grabs the lock without
    // blocking and reuses cached timers if the currency scan holds it. The currency
    // loop additionally pauses while a timer is active, so in steady state during
    // an event the two never contend.
    //
    // The scan used to take ~150s because IsEventTicket read entry.Card per entry;
    // it is now a single round trip, so this contention is far milder than when
    // the machinery was written. It is kept because one round trip is still not
    // free and the timer must stay at second-level freshness.
    using var sdkLock = new SemaphoreSlim(1, 1);

    await RunWatchTasksAsync(
        sdkLock,
        snapshot => Console.WriteLine(JsonSerializer.Serialize(snapshot, options)),
        timerInterval.Value,
        currencyInterval.Value,
        cts.Token);
}

// The watch loops themselves, decoupled from how their snapshots leave the
// process and from who owns the SDK lock. Standalone `watch` mode writes each
// snapshot straight to stdout; `serve` mode wraps it in a push event and shares
// its one SDK lock with in-flight requests, so a watch subscription and a
// collection refresh never contend across two attached processes.
static async Task RunWatchTasksAsync(
    SemaphoreSlim sdkLock,
    Action<WatchSnapshot> emit,
    TimeSpan timerInterval,
    TimeSpan currencyInterval,
    CancellationToken ct)
{
    var cache = new WatchCache();
    // Linked so that one loop dying (cancellation or fatal error) tears the other
    // down instead of leaving it spinning against a half-dead SDK attach.
    using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
    var token = cts.Token;

    // Task.Run so each loop gets its own thread: the SDK reads are synchronous
    // blocking calls, and SemaphoreSlim.WaitAsync completes synchronously on a
    // free lock, so without this the first loop would run inline (through its
    // slow first scan) before the second ever started.
    var currencyTask = Task.Run(
        () => RunCurrencyRefreshLoopAsync(sdkLock, cache, currencyInterval, token),
        token);
    var timerTask = Task.Run(
        () => RunChallengeTimerLoopAsync(emit, sdkLock, cache, timerInterval, token),
        token);

    try
    {
        await Task.WhenAny(currencyTask, timerTask);
    }
    finally
    {
        cts.Cancel();
        try
        {
            await Task.WhenAll(currencyTask, timerTask);
        }
        catch (OperationCanceledException)
        {
            // Expected on shutdown.
        }
    }
}

// Drives output cadence. Emits one snapshot per tick carrying fresh challenge
// timers plus the most recently cached currency. Uses a non-blocking lock
// acquisition so a long currency scan never stalls timer output: if the lock is
// busy it reuses the previous timer reading for that tick.
static async Task RunChallengeTimerLoopAsync(
    Action<WatchSnapshot> emit,
    SemaphoreSlim sdkLock,
    WatchCache cache,
    TimeSpan interval,
    CancellationToken ct)
{
    var primed = false;
    while (!ct.IsCancellationRequested)
    {
        string? error = null;
        // Until the first reading lands, block for the lock so the timer loop owns
        // the cold attach; afterwards use a non-blocking grab so the periodic
        // currency scan can never stall timer output (it reuses cached timers).
        var gotLock = primed ? await sdkLock.WaitAsync(0, ct) : await TryAcquireAsync(sdkLock, ct);
        if (gotLock)
        {
            try
            {
                cache.Timers = GetChallengeTimers();
                cache.HasActiveTimer = cache.Timers.Count > 0;
            }
            catch (Exception ex)
            {
                error = ex.Message;
            }
            finally
            {
                // Prime after the first acquired attempt (success or failure) so
                // the cold attach is paid here and the currency loop can proceed.
                if (!primed)
                {
                    primed = true;
                    cache.MarkPrimed();
                }
                sdkLock.Release();
            }
        }

        emit(new WatchSnapshot(DateTimeOffset.UtcNow, cache.Timers, cache.Currency, error));

        try
        {
            await Task.Delay(interval, ct);
        }
        catch (TaskCanceledException)
        {
            break;
        }
    }
}

// Blocking lock acquisition that reports cancellation as a bool instead of throwing.
static async Task<bool> TryAcquireAsync(SemaphoreSlim sdkLock, CancellationToken ct)
{
    try
    {
        await sdkLock.WaitAsync(ct);
        return true;
    }
    catch (OperationCanceledException)
    {
        return false;
    }
}

// Refreshes the cached currency on a coarse cadence. Holds the SDK lock for the
// duration of the scan (one round trip, ~0.9-1.3s); the timer loop keeps
// emitting meanwhile.
static async Task RunCurrencyRefreshLoopAsync(
    SemaphoreSlim sdkLock,
    WatchCache cache,
    TimeSpan interval,
    CancellationToken ct)
{
    // How often to re-check the active-timer flag while paused.
    var pausePoll = TimeSpan.FromSeconds(5);

    // Let the timer loop take (and warm) the SDK first so its initial reading
    // isn't queued behind a full currency scan.
    try
    {
        await cache.Primed.WaitAsync(ct);
    }
    catch (OperationCanceledException)
    {
        return;
    }

    while (!ct.IsCancellationRequested)
    {
        // Pause while a challenge timer is being tracked. A currency scan blocks
        // the timer's reads on MTGO's UI thread (concurrent SDK calls don't help —
        // they queue server-side), so we simply don't scan while an event is live.
        // Resume once no timer is active.
        if (cache.HasActiveTimer)
        {
            try
            {
                await Task.Delay(pausePoll, ct);
            }
            catch (TaskCanceledException)
            {
                break;
            }
            continue;
        }

        await sdkLock.WaitAsync(ct);
        try
        {
            cache.Currency = GetCurrencySnapshot();
        }
        catch (Exception ex)
        {
            cache.Currency = new CurrencySnapshot(null, null, null, ex.Message);
        }
        finally
        {
            sdkLock.Release();
        }

        try
        {
            await Task.Delay(interval, ct);
        }
        catch (TaskCanceledException)
        {
            break;
        }
    }
}

// ---------------------------------------------------------------- serve mode
//
// One long-lived process that answers newline-delimited JSON requests on stdin
// with newline-delimited JSON on stdout. Motivation (measured against a live
// client): a one-shot invocation pays ~0.8s of .NET startup plus ~3.1s of
// RemoteClient attach *before* it does any work, so a three-command probe cycle
// spent ~90% of its wall time on overhead; and several bridge processes attached
// at once degrade per-call latency ~8x, because MTGOSDK marshals every read onto
// MTGO's UI thread. Keeping one process with one request queue pays the attach
// once and removes the cross-process contention structurally.
//
// Protocol (one JSON object per line, both directions):
//   ->  {"id":"7","command":"collection","args":[]}
//   <-  {"id":"7","ok":true,"payload":{...}}            // payload == CLI output
//   <-  {"id":"7","ok":false,"error":"..."}
//   <-  {"event":"ready","payload":{"protocol":1,"pid":1234}}
//   <-  {"event":"watch","payload":{...WatchSnapshot...}}
//   <-  {"event":"disconnected","payload":{"reason":"..."}}
// Closing stdin shuts the process down; an older build without this mode exits
// immediately without a ready banner, which is how the client detects it.
static void RunServeLoop(JsonSerializerOptions options)
{
    Console.OutputEncoding = Encoding.UTF8;

    var stdoutLock = new object();
    void Emit(object payload)
    {
        var line = JsonSerializer.Serialize(payload, options);
        lock (stdoutLock)
        {
            // Write the newline separately: WriteLine would emit "\r\n" on
            // Windows and the client splits strictly on "\n".
            Console.Out.Write(line);
            Console.Out.Write('\n');
            Console.Out.Flush();
        }
    }

    using var cts = new CancellationTokenSource();
    // One lock, one queue: every SDK touch in this process — requests and the
    // watch loops alike — is serialised through here, which is the whole point.
    using var sdkLock = new SemaphoreSlim(1, 1);
    using var requests = new BlockingCollection<ServeRequest>(new ConcurrentQueue<ServeRequest>());

    var worker = new Thread(() => RunServeWorker(requests, sdkLock, Emit, cts.Token))
    {
        IsBackground = true,
        Name = "bridge-serve-worker",
    };
    worker.Start();

    var watchdog = new Thread(() => RunMtgoWatchdog(Emit, cts.Token))
    {
        IsBackground = true,
        Name = "bridge-mtgo-watchdog",
    };
    watchdog.Start();

    Emit(new ServeEvent(
        "ready",
        new ServeReadyPayload(ServeProtocol.Version, Environment.ProcessId)));

    string? line;
    while ((line = Console.In.ReadLine()) != null)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            continue;
        }

        var (request, id, error) = ParseServeRequest(line);
        if (request is null)
        {
            Emit(new ServeResponse(id, false, null, error));
            continue;
        }

        requests.Add(request);
    }

    // stdin closed: the supervising client is gone (or asked us to stop). Give
    // the worker a moment to unwind, then fall off the end — the remaining
    // threads are background threads, so the process exits. Nothing is buffered
    // that needs flushing, and one-shot invocations already exit mid-attach.
    requests.CompleteAdding();
    cts.Cancel();
    worker.Join(TimeSpan.FromSeconds(2));
}

// Executes queued requests strictly one at a time. Watch start/stop is handled
// here too, so the subscription's lifetime needs no extra synchronisation.
static void RunServeWorker(
    BlockingCollection<ServeRequest> requests,
    SemaphoreSlim sdkLock,
    Action<object> emit,
    CancellationToken ct)
{
    CancellationTokenSource? watchCts = null;
    Task? watchTask = null;

    // Cancelling is instant; joining is not, because a loop blocked inside a
    // synchronous SDK read cannot observe the token until that read returns.
    // So `watch stop` only signals — the answer goes out immediately — and the
    // join is deferred to the next `watch start`, which is rare.
    void CancelWatchTasks() => watchCts?.Cancel();

    void ReapWatchTasks()
    {
        if (watchCts is null)
        {
            return;
        }

        watchCts.Cancel();
        try
        {
            watchTask?.Wait(TimeSpan.FromSeconds(5));
        }
        catch (AggregateException)
        {
            // Cancellation surfaces here; nothing to report.
        }

        watchCts.Dispose();
        watchCts = null;
        watchTask = null;
    }

    try
    {
        foreach (var request in requests.GetConsumingEnumerable())
        {
            try
            {
                if (request.Mode == ExecutionMode.Watch)
                {
                    if (ParseWatchCommand(request.Argv) == WatchCommand.Stop)
                    {
                        CancelWatchTasks();
                        emit(new ServeResponse(request.Id, true, new ServeAck("watch.stopped"), null));
                        continue;
                    }

                    ReapWatchTasks();
                    watchCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                    watchTask = RunWatchTasksAsync(
                        sdkLock,
                        snapshot => emit(new ServeEvent("watch", snapshot)),
                        TimeSpan.FromMilliseconds(ParseWatchIntervalMs(request.Argv)),
                        TimeSpan.FromMinutes(10),
                        watchCts.Token);
                    emit(new ServeResponse(request.Id, true, new ServeAck("watch.started"), null));
                    continue;
                }

                sdkLock.Wait(ct);
                try
                {
                    emit(new ServeResponse(
                        request.Id,
                        true,
                        BuildPayload(request.Mode, request.Argv),
                        null));
                }
                finally
                {
                    sdkLock.Release();
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                emit(new ServeResponse(request.Id, false, null, ex.GetBaseException().Message));
            }
        }
    }
    finally
    {
        CancelWatchTasks();
    }
}

// MTGO can exit and restart underneath a long-lived attach, and MTGOSDK gives no
// usable signal for that. Polling the local process list costs nothing (no IPC),
// so the daemon simply stops once the client it attached to is gone: the Python
// supervisor sees the event plus EOF and respawns against the new MTGO.
static void RunMtgoWatchdog(Action<object> emit, CancellationToken ct)
{
    var seenRunning = false;
    while (!ct.IsCancellationRequested)
    {
        var processes = Process.GetProcessesByName("MTGO");
        var running = processes.Length > 0;
        foreach (var process in processes)
        {
            process.Dispose();
        }

        if (running)
        {
            seenRunning = true;
        }
        else if (seenRunning)
        {
            emit(new ServeEvent(
                "disconnected",
                new ServeReasonPayload("MTGO process exited")));
            // stdin is blocked in ReadLine on the main thread and cannot be
            // interrupted, so exit outright. The banner above has already been
            // flushed, and the client treats EOF as "respawn on next request".
            Environment.Exit(0);
        }

        ct.WaitHandle.WaitOne(TimeSpan.FromSeconds(5));
    }
}

// Returns the parsed request, or the id (when recoverable) plus an error string.
static (ServeRequest? Request, string? Id, string? Error) ParseServeRequest(string line)
{
    string? id = null;
    try
    {
        using var document = JsonDocument.Parse(line);
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
        {
            return (null, null, "Request must be a JSON object.");
        }

        if (root.TryGetProperty("id", out var idElement) && idElement.ValueKind == JsonValueKind.String)
        {
            id = idElement.GetString();
        }

        if (!root.TryGetProperty("command", out var commandElement)
            || commandElement.ValueKind != JsonValueKind.String)
        {
            return (null, id, "Request is missing a string 'command'.");
        }

        var command = commandElement.GetString() ?? string.Empty;
        var argv = new List<string> { command };
        if (root.TryGetProperty("args", out var argsElement)
            && argsElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var arg in argsElement.EnumerateArray())
            {
                argv.Add(arg.ValueKind == JsonValueKind.String
                    ? arg.GetString() ?? string.Empty
                    : arg.ToString());
            }
        }

        var mode = ParseMode(argv.ToArray());
        if (mode == ExecutionMode.None)
        {
            return (null, id, $"Unknown command '{command}'.");
        }

        if (mode == ExecutionMode.Serve)
        {
            return (null, id, "'serve' cannot be nested inside a serve session.");
        }

        return (new ServeRequest(id, mode, argv.ToArray()), id, null);
    }
    catch (JsonException ex)
    {
        return (null, id, $"Invalid JSON request: {ex.Message}");
    }
}

static WatchCommand ParseWatchCommand(string[] argv)
{
    if (argv.Length <= 1)
    {
        return WatchCommand.Start;
    }

    var token = (argv[1] ?? string.Empty).Trim().TrimStart('-', '/').ToLowerInvariant();
    return token is "stop" or "cancel" ? WatchCommand.Stop : WatchCommand.Start;
}

// ``watch [start] [intervalMs]`` — falls back to the standalone mode's cadence.
static int ParseWatchIntervalMs(string[] argv)
{
    foreach (var token in argv.Skip(1))
    {
        if (int.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
            && value > 0)
        {
            return Math.Max(value, 100);
        }
    }

    return 500;
}

static IReadOnlyList<ChallengeTimerSnapshot> GetChallengeTimers()
{
    var results = new List<ChallengeTimerSnapshot>();
    
    foreach (var evt in SnapshotEnumerable(EventManager.JoinedEvents))
    {
        switch (evt)
        {
            case null:
                continue;
            case Match match:
                continue;
            case Tournament tournament:
                double? seconds = null;
                var tournamentTimer = SafeGet<object>(evt, "TimeRemaining");
                seconds = ConvertToDouble(SafeGet(tournamentTimer, "TotalSeconds", 0.0));
                results.Add(new ChallengeTimerSnapshot(
                    EventId: SafeGet(evt, "Id", SafeGet(evt, "EventId", "No event Id found")),
                    Description: SafeGet(evt, "Description", "No event description found"),
                    Format: SafeGet(evt, "Format", "No format found"),
                    RemainingSeconds: seconds,
                    State: SafeGet(evt, "State", SafeGet(evt, "Status", "No state found"))
                ));
                continue;
            case League league:
                continue;
        }
    }
    return results;
}

static bool IsEventTicket(CardQuantityPair? entry)
{
    if (entry is null)
    {
        return false;
    }

    // Do NOT read entry.Card here. GetFrozenCollection populates Id/Name/Quantity
    // locally at zero IPC cost, but entry.Card forces a remote round trip per
    // entry: CardDataManager.GetCardDefinitionForCatId (~54.8ms) followed by
    // MagicEntityDefinition.get_IsTicket (~17.2ms). Measured against a
    // 2,069-card collection that was ~150s per scan and 69% of all MTGOSDK IPC
    // traffic in a 54-minute session, to produce three integers. The name match
    // below already answers the question, and RunCurrencyRefreshLoopAsync runs
    // this every 10 minutes while the user may be in a game.
    return MatchesName(entry.Name, "Event Ticket", "Event Tickets");
}

static bool IsPlayPoints(CardQuantityPair? entry)
{
    if (entry is null)
    {
        return false;
    }

    return MatchesName(entry.Name, "Play Point", "Play Points");
}

static bool IsTreasureChest(CardQuantityPair? entry)
{
    if (entry is null)
    {
        return false;
    }

    // MTGO labels both "Treasure Chest" and "Treasure Chest Booster"
    return MatchesName(entry.Name, "Treasure Chest", "Treasure Chest Booster", "Treasure Chest Boosters");
}

static bool MatchesName(string? candidate, params string[] expectedValues)
{
    if (string.IsNullOrWhiteSpace(candidate))
    {
        return false;
    }

    foreach (var expected in expectedValues)
    {
        if (candidate.Equals(expected, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }
    }

    return false;
}

static IReadOnlyList<object?> SnapshotEnumerable(object? candidate)
{
    if (candidate is null)
    {
        return Array.Empty<object?>();
    }

    if (candidate is string or byte[])
    {
        return new object?[] { candidate };
    }

    if (candidate is IEnumerable enumerable)
    {
        var list = new List<object?>();
        foreach (var item in enumerable)
        {
            list.Add(item);
        }
        return list;
    }

    return new object?[] { candidate };
}


static double? ConvertToDouble(object? value)
{
    if (value is null)
    {
        return null;
    }

    switch (value)
    {
        case double d:
            return d;
        case float f:
            return f;
        case decimal dec:
            return (double)dec;
        case int i:
            return i;
        case long l:
            return l;
        case TimeSpan span:
            return span.TotalSeconds;
        case string s when double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed):
            return parsed;
        default:
            try
            {
                var converted = Convert.ToDouble(value, CultureInfo.InvariantCulture);
                return converted;
            }
            catch
            {
                return null;
            }
    }
}

static ExecutionMode ParseMode(string[] args)
{
    if (args.Length == 0)
    {
        return ExecutionMode.None;
    }

    var token = args[0]?.Trim() ?? string.Empty;
    token = token.TrimStart('-', '/');
    if (token.Length == 0)
    {
        return ExecutionMode.None;
    }

    return token.ToLowerInvariant() switch
    {
        "collection" or "collect" => ExecutionMode.Collection,
        "all" or "both" => ExecutionMode.All,
        "currency" or "wallet" or "tickets" or "points" => ExecutionMode.Currency,
        "watch" or "monitor" => ExecutionMode.Watch,
        "logfiles" or "logs" => ExecutionMode.LogFiles,
        "username" or "user" or "name" => ExecutionMode.Username,
        "trade" or "trades" => ExecutionMode.Trade,
        "serve" or "daemon" => ExecutionMode.Serve,
        "ping" => ExecutionMode.Ping,
        _ => ExecutionMode.None,
    };
}

static TradeCommand ParseTradeCommand(string[] args)
{
    if (args.Length <= 1)
    {
        return TradeCommand.Status;
    }

    var token = args[1]?.Trim() ?? string.Empty;
    token = token.TrimStart('-', '/').ToLowerInvariant();
    return token switch
    {
        "accept" or "approve" => TradeCommand.Accept,
        _ => TradeCommand.Status,
    };
}

static TradeStatusPayload GetTradeStatusSnapshot()
{
    try
    {
        var trade = TradeManager.CurrentTrade;
        if (trade is null)
        {
            return new TradeStatusPayload(
                DateTimeOffset.UtcNow,
                new TradeSnapshot(
                    false,
                    null,
                    null,
                    null,
                    null,
                    null,
                    Array.Empty<TradeItemSnapshot>(),
                    Array.Empty<TradeItemSnapshot>(),
                    Array.Empty<TradeItemSnapshot>(),
                    "No active trade session"
                )
            );
        }

        var partner = trade.TradePartner;
        var partnerSnapshot = partner is null
            ? null
            : new TradeParticipantSnapshot(
                SafeGet<int?>(partner, "Id"),
                SafeGet(partner, "Name", null as string),
                SafeGet<bool?>(partner, "IsBuddy"),
                SafeGet<bool?>(partner, "IsBlocked"),
                SafeGet<bool?>(partner, "IsGuest"),
                SafeGet<bool?>(partner, "IsLoggedIn")
            );

        TradeBinderSnapshot? binderSnapshot = null;
        try
        {
            var binder = trade.ActiveBinder;
            binderSnapshot = binder is null
                ? null
                : new TradeBinderSnapshot(
                    SafeGet(binder, "Id", 0),
                    SafeGet(binder, "Name", null as string),
                    SafeGet(binder, "ItemCount", 0),
                    SafeGet(binder, "MaxItems", 0),
                    SafeGet(binder, "Hash", null as string)
                );
        }
        catch
        {
            binderSnapshot = null;
        }

        return new TradeStatusPayload(
            DateTimeOffset.UtcNow,
            new TradeSnapshot(
                true,
                trade.State.ToString(),
                trade.FinalState.ToString(),
                trade.IsAccepted,
                partnerSnapshot,
                binderSnapshot,
                SnapshotTradeItems(trade.TradedItems),
                SnapshotTradeItems(trade.PartnerTradedItems),
                SnapshotTradeItems(trade.TradeableItems),
                null
            )
        );
    }
    catch (Exception ex)
    {
        return new TradeStatusPayload(
            DateTimeOffset.UtcNow,
            new TradeSnapshot(
                false,
                null,
                null,
                null,
                null,
                null,
                Array.Empty<TradeItemSnapshot>(),
                Array.Empty<TradeItemSnapshot>(),
                Array.Empty<TradeItemSnapshot>(),
                ex.Message
            )
        );
    }
}

static TradeAcceptSnapshot AcceptTradeSnapshot()
{
    try
    {
        var trade = TradeManager.CurrentTrade;
        if (trade is null)
        {
            return new TradeAcceptSnapshot(
                DateTimeOffset.UtcNow,
                false,
                false,
                "No active trade session"
            );
        }

        // MTGOSDK currently documents read-only trade access, so we cannot
        // trigger acceptance without additional client binding hooks.
        return new TradeAcceptSnapshot(
            DateTimeOffset.UtcNow,
            true,
            trade.IsAccepted,
            "Trade acceptance is not supported by MTGOSDK (see docs/api-reference.md#trade)"
        );
    }
    catch (Exception ex)
    {
        return new TradeAcceptSnapshot(
            DateTimeOffset.UtcNow,
            false,
            false,
            ex.Message
        );
    }
}

static IReadOnlyList<TradeItemSnapshot> SnapshotTradeItems(object? candidate)
{
    if (candidate is null)
    {
        return Array.Empty<TradeItemSnapshot>();
    }

    try
    {
        var entries = candidate switch
        {
            ItemCollection itemCollection => SnapshotEnumerable(itemCollection.CollectionItems),
            IEnumerable enumerable => SnapshotEnumerable(enumerable),
            _ => SnapshotEnumerable(candidate)
        };

        var list = new List<TradeItemSnapshot>();
        foreach (var entry in entries)
        {
            if (entry is null)
            {
                continue;
            }

            var card = SafeGet<object?>(entry, "Card", SafeGet(entry, "CardDefinition", null as object));
            var id = SafeGet(entry, "Id", SafeGet(card, "Id", SafeGet(entry, "CatalogId", 0)));
            var name = SafeGet(entry, "Name", SafeGet(card, "Name", null as string));
            var quantity = SafeGet(entry, "Quantity", SafeGet(entry, "Count", SafeGet(entry, "Amount", 0)));
            if (quantity <= 0)
            {
                quantity = 1;
            }
            var lockedQuantity = SafeGet(entry, "LockedQuantity", SafeGet(entry, "ReservedQuantity", (int?)null));
            var isTicket = SafeGet<bool?>(entry, "IsTicket", SafeGet(card, "IsTicket", null as bool?));
            var isFoil = SafeGet<bool?>(entry, "IsFoil", SafeGet(card, "IsPremium", null as bool?));
            var isTradable = SafeGet<bool?>(entry, "IsTradable", SafeGet(card, "IsTradable", null as bool?));

            list.Add(new TradeItemSnapshot(
                id,
                name,
                quantity,
                lockedQuantity,
                isTicket,
                isFoil,
                isTradable
            ));
        }

        return list;
    }
    catch
    {
        return Array.Empty<TradeItemSnapshot>();
    }
}

enum ExecutionMode
{
    None = 0,
    Collection,
    All,
    Currency,
    Watch,
    LogFiles,
    Username,
    Trade,
    Serve,
    Ping,
}

enum TradeCommand
{
    Status = 0,
    Accept,
}

enum WatchCommand
{
    Start = 0,
    Stop,
}

static class ServeProtocol
{
    // Bumped only on a breaking change to the stdin/stdout envelope; the client
    // refuses a version it does not know and falls back to one-shot commands.
    public const int Version = 1;
}

sealed record ServeRequest(string? Id, ExecutionMode Mode, string[] Argv);

public sealed record ServeResponse(
    string? Id,
    bool Ok,
    object? Payload,
    string? Error
);

public sealed record ServeEvent(string Event, object? Payload);

public sealed record ServeReadyPayload(int Protocol, int Pid);

public sealed record ServeReasonPayload(string Reason);

public sealed record ServeAck(string Status);

public sealed record PingSnapshot(bool Ok, DateTimeOffset Timestamp);

public sealed record ChallengeTimerSnapshot(
    string? EventId,
    string? Description,
    string? Format,
    double? RemainingSeconds,
    string? State
);

public sealed record CurrencySnapshot(
    int? EventTickets,
    int? PlayPoints,
    int? TreasureChests,
    string? Error
);

public sealed record WatchSnapshot(
    DateTimeOffset Timestamp,
    IReadOnlyList<ChallengeTimerSnapshot> ChallengeTimers,
    CurrencySnapshot? Currency,
    string? Error
);

// Shared between the watch loops: the timer loop publishes fresh timers and reads
// the currency the currency loop publishes. Fields are volatile because the loops
// run on different tasks; record/list references are assigned atomically.
sealed class WatchCache
{
    private volatile IReadOnlyList<ChallengeTimerSnapshot> _timers =
        Array.Empty<ChallengeTimerSnapshot>();
    private volatile CurrencySnapshot? _currency;
    private volatile bool _hasActiveTimer;
    private readonly TaskCompletionSource _primed =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    public IReadOnlyList<ChallengeTimerSnapshot> Timers
    {
        get => _timers;
        set => _timers = value;
    }

    // True while at least one challenge timer is being tracked. The currency loop
    // watches this and pauses: the SDK serialises reads on MTGO's UI thread, so a
    // currency scan would otherwise delay fresh timer reads. Pausing gives the
    // timer exclusive, uninterrupted access whenever an event is live.
    public bool HasActiveTimer
    {
        get => _hasActiveTimer;
        set => _hasActiveTimer = value;
    }

    public CurrencySnapshot? Currency
    {
        get => _currency;
        set => _currency = value;
    }

    // Completes once the timer loop has taken its first SDK reading. The currency
    // loop waits on this so the (slow, cold) initial SDK attach is paid by the
    // priority timer read instead of the currency scan monopolising startup.
    public Task Primed => _primed.Task;

    public void MarkPrimed() => _primed.TrySetResult();
}

public sealed record CollectionCard(int Id, string Name, int Quantity);

public sealed record CollectionSnapshot(
    int Id,
    string? Name,
    int ItemCount,
    int MaxItems,
    IReadOnlyList<CollectionCard> Items,
    string? Error
);

public sealed record LogFilesSnapshot(
    IReadOnlyList<string> Files,
    string? Error
);

public sealed record UsernameSnapshot(
    // Always emit "username", even when null. The serializer's global
    // WhenWritingNull policy otherwise omits the key entirely, and the Python
    // caller's data.get("username") then can't tell "bridge failed" from
    // "no username" — which is how this failure stayed silent.
    [property: JsonIgnore(Condition = JsonIgnoreCondition.Never)] string? Username,
    string? Error
);

public sealed record BridgePayload(
    DateTimeOffset Timestamp,
    string Mode,
    CollectionSnapshot? Collection,
    CurrencySnapshot? Currency,
    IReadOnlyDictionary<string, long> Timings
);

public sealed record TradeStatusPayload(
    DateTimeOffset Timestamp,
    TradeSnapshot Trade
);

public sealed record TradeSnapshot(
    bool HasActiveTrade,
    string? State,
    string? FinalState,
    bool? IsAccepted,
    TradeParticipantSnapshot? Partner,
    TradeBinderSnapshot? Binder,
    IReadOnlyList<TradeItemSnapshot> LocalItems,
    IReadOnlyList<TradeItemSnapshot> PartnerItems,
    IReadOnlyList<TradeItemSnapshot> TradeableItems,
    string? Error
);

public sealed record TradeParticipantSnapshot(
    int? Id,
    string? Name,
    bool? IsBuddy,
    bool? IsBlocked,
    bool? IsGuest,
    bool? IsLoggedIn
);

public sealed record TradeBinderSnapshot(
    int Id,
    string? Name,
    int ItemCount,
    int MaxItems,
    string? Hash
);

public sealed record TradeItemSnapshot(
    int Id,
    string? Name,
    int Quantity,
    int? LockedQuantity,
    bool? IsTicket,
    bool? IsFoil,
    bool? IsTradable
);

public sealed record TradeAcceptSnapshot(
    DateTimeOffset Timestamp,
    bool RequestedAcceptance,
    bool Accepted,
    string? Error
);
