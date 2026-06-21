using System;
using System.Collections;
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

if (mode == ExecutionMode.LogFiles)
{
    var logFilesPayload = GetLogFilesSnapshot();
    var logFilesSerialized = JsonSerializer.Serialize(logFilesPayload, jsonOptions);
    Console.WriteLine(logFilesSerialized);
    return;
}

if (mode == ExecutionMode.Username)
{
    var usernamePayload = GetUsernameSnapshot();
    var usernameSerialized = JsonSerializer.Serialize(usernamePayload, jsonOptions);
    Console.WriteLine(usernameSerialized);
    return;
}

if (mode == ExecutionMode.Trade)
{
    var tradeCommand = ParseTradeCommand(args);
    if (tradeCommand == TradeCommand.Accept)
    {
        var acceptPayload = AcceptTradeSnapshot();
        var acceptSerialized = JsonSerializer.Serialize(acceptPayload, jsonOptions);
        Console.WriteLine(acceptSerialized);
        return;
    }

    var tradePayload = GetTradeStatusSnapshot();
    var tradeSerialized = JsonSerializer.Serialize(tradePayload, jsonOptions);
    Console.WriteLine(tradeSerialized);
    return;
}

var timings = new Dictionary<string, long>(StringComparer.OrdinalIgnoreCase);
var totalStopwatch = Stopwatch.StartNew();

CollectionSnapshot? collectionSnapshot = null;
HistorySnapshot? historySnapshot = null;
CurrencySnapshot? currencySnapshot = null;

if (mode is ExecutionMode.Collection or ExecutionMode.All)
{
    collectionSnapshot = Measure("collectionMs", GetCollectionSnapshot, timings);
}

if (mode is ExecutionMode.History or ExecutionMode.All)
{
    historySnapshot = Measure("historyMs", GetHistorySnapshot, timings);
}

if (mode is ExecutionMode.Currency or ExecutionMode.All)
{
    currencySnapshot = Measure("currencyMs", GetCurrencySnapshot, timings);
}

totalStopwatch.Stop();
timings["totalMs"] = totalStopwatch.ElapsedMilliseconds;

var payload = new BridgePayload(
    DateTimeOffset.UtcNow,
    mode.ToString(),
    collectionSnapshot,
    historySnapshot,
    currencySnapshot,
    timings
);

var serialized = JsonSerializer.Serialize(payload, jsonOptions);

// Observed timings with ~2,290 cards and 270 matches (2024-xx-xx):
// collectionMs ≈ 3_728, historyMs ≈ 17_280, totalMs ≈ 21_009
Console.WriteLine(serialized);

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
    try
    {
        // Strategy 1: Try to get from Client.CurrentUser using reflection
        var clientType = Type.GetType("MTGOSDK.API.Client, MTGOSDK");
        if (clientType != null)
        {
            var currentUserProp = clientType.GetProperty("CurrentUser", BindingFlags.Public | BindingFlags.Static);
            if (currentUserProp != null)
            {
                var currentUser = currentUserProp.GetValue(null);
                if (currentUser != null)
                {
                    var name = SafeGet(currentUser, "Name", string.Empty);
                    if (!string.IsNullOrWhiteSpace(name))
                    {
                        return new UsernameSnapshot(name, null);
                    }
                }
            }
        }

        // Strategy 2: Try UserManager.CurrentUser
        var userManagerType = Type.GetType("MTGOSDK.API.Users.UserManager, MTGOSDK");
        if (userManagerType != null)
        {
            var currentUserProp = userManagerType.GetProperty("CurrentUser", BindingFlags.Public | BindingFlags.Static);
            if (currentUserProp != null)
            {
                var currentUser = currentUserProp.GetValue(null);
                if (currentUser != null)
                {
                    var name = SafeGet(currentUser, "Name", string.Empty);
                    if (!string.IsNullOrWhiteSpace(name))
                    {
                        return new UsernameSnapshot(name, null);
                    }
                }
            }
        }

        // Strategy 3: Get username from collection name
        var collection = CollectionManager.Collection;
        if (collection != null)
        {
            var collectionName = collection.Name;
            if (!string.IsNullOrWhiteSpace(collectionName) && collectionName != "Collection")
            {
                // Collection name might be the username
                return new UsernameSnapshot(collectionName, null);
            }
        }

        return new UsernameSnapshot(null, "Could not determine current user");
    }
    catch (Exception ex)
    {
        return new UsernameSnapshot(null, ex.Message);
    }
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

static HistorySnapshot GetHistorySnapshot()
{
    bool historyLoaded = false;

    // ReadGameHistory() can throw from inside MTGOSDK (e.g. a RuntimeBinderException
    // when the remote dynamic type drifts from the SDK's expectations). Guard it so a
    // single failing snapshot returns a structured error instead of crashing the whole
    // process and corrupting the JSON contract the Python side parses.
    try
    {
        // ReadGameHistory() returns the full list - use it directly instead of accessing .Items!
        var rawItems = HistoryManager.ReadGameHistory();
        if (rawItems == null)
        {
            return new HistorySnapshot(historyLoaded, Array.Empty<HistoryEntry>(), "History items is null");
        }

        var items = rawItems
            .Select(item => MapHistoryItem(item))
            .Where(entry => entry != null)
            .Cast<HistoryEntry>()
            .ToList();
        return new HistorySnapshot(historyLoaded, items, null);
    }
    catch (Exception ex)
    {
        return new HistorySnapshot(historyLoaded, Array.Empty<HistoryEntry>(), ex.Message);
    }
}

static HistoryEntry? MapHistoryItem(object? item)
{
    if (item is null)
    {
        return null;
    }

    var type = item.GetType();
    var typeName = type.Name;

    // Extract basic properties using reflection - no type casting
    var id = SafeGet<int>(item, "Id");
    var startTime = SafeGet(item, "StartTime", DateTime.MinValue);

    // Handle HistoricalMatch
    if (typeName == "HistoricalMatch")
    {
        var opponents = ExtractOpponentNames(item);
        var gameWins = SafeGet<int?>(item, "GameWins");
        var gameLosses = SafeGet<int?>(item, "GameLosses");
        var gameTies = SafeGet<int?>(item, "GameTies");
        var gameIds = ExtractGameIds(item);
        return new HistoryEntry(
            "match",
            id,
            startTime,
            opponents,
            gameWins,
            gameLosses,
            gameTies,
            gameIds,
            null,
            null,
            null
        );
    }

    // Handle HistoricalTournament
    if (typeName == "HistoricalTournament")
    {
        var matches = ExtractTournamentMatches(item);
        var matchWins = SafeGet<int?>(item, "MatchWins");
        var matchLosses = SafeGet<int?>(item, "MatchLosses");
        return new HistoryEntry(
            "tournament",
            id,
            startTime,
            Array.Empty<string>(),
            null,
            null,
            null,
            null,
            matches,
            matchWins,
            matchLosses
        );
    }

    // Default fallback
    return new HistoryEntry(
        typeName,
        id,
        startTime,
        Array.Empty<string>(),
        null,
        null,
        null,
        null,
        null,
        null,
        null
    );
}

static IReadOnlyList<string> ExtractOpponentNames(object match)
{
    var result = new List<string>();

    if (match == null)
    {
        return result;
    }

    var type = match.GetType();

    // STRATEGY 1: Access raw backing object before SDK converts to User objects
    // HistoricalMatch has an internal "obj" field that contains the raw dynamic data
    try
    {
        // Try to get the internal "obj" field (contains the raw dynamic object)
        var objField = type.GetField("obj", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        if (objField != null)
        {
            var rawObj = objField.GetValue(match);
            if (rawObj != null)
            {
                // Access Opponents on the raw dynamic object (should be strings, not User objects)
                var rawType = rawObj.GetType();
                var rawOpponentsProp = rawType.GetProperty("Opponents");
                if (rawOpponentsProp != null)
                {
                    try
                    {
                        var rawOpponents = rawOpponentsProp.GetValue(rawObj);
                        if (rawOpponents is IEnumerable rawEnum)
                        {
                            foreach (var item in rawEnum)
                            {
                                // The raw data might be strings directly
                                if (item is string str && !string.IsNullOrWhiteSpace(str))
                                {
                                    result.Add(str.Trim());
                                }
                                // Or might be dynamic objects with string properties
                                else if (item != null)
                                {
                                    // Try to get string representation or Name property
                                    var itemType = item.GetType();
                                    var nameProp = itemType.GetProperty("Name");
                                    if (nameProp != null)
                                    {
                                        var nameValue = nameProp.GetValue(item);
                                        if (nameValue is string name && !string.IsNullOrWhiteSpace(name))
                                        {
                                            result.Add(name.Trim());
                                        }
                                    }
                                    else
                                    {
                                        // Fallback to ToString
                                        var strVal = item.ToString();
                                        if (!string.IsNullOrWhiteSpace(strVal))
                                        {
                                            result.Add(strVal.Trim());
                                        }
                                    }
                                }
                            }

                            // If we got results from raw data, return them
                            if (result.Count > 0)
                            {
                                return result;
                            }
                        }
                    }
                    catch
                    {
                        // Raw access failed, try other strategies
                    }
                }
            }
        }
    }
    catch
    {
        // Strategy 1 failed, continue to strategy 2
    }

    // STRATEGY 2: Try the SDK's Opponents property (might work if data is valid)
    object? opponents = null;
    try
    {
        var opponentsProp = type.GetProperty("Opponents", BindingFlags.Public | BindingFlags.Instance);
        if (opponentsProp != null)
        {
            try
            {
                opponents = opponentsProp.GetValue(match);
            }
            catch (TargetInvocationException)
            {
                // SDK conversion failed - this is expected
                opponents = null;
            }
            catch
            {
                opponents = null;
            }
        }
    }
    catch
    {
        // Property lookup failed
    }

    // If SDK property worked, extract User names
    if (opponents != null && opponents is IEnumerable enumerable)
    {
        foreach (var opponent in enumerable)
        {
            if (opponent == null) continue;

            string? name = null;
            var opponentType = opponent.GetType();

            // Try to get Name property
            try
            {
                var nameProp = opponentType.GetProperty("Name", BindingFlags.Public | BindingFlags.Instance);
                if (nameProp != null)
                {
                    var nameValue = nameProp.GetValue(opponent);
                    name = nameValue as string;
                }
            }
            catch
            {
                // Try method invocation
                try
                {
                    var getName = opponentType.GetMethod("get_Name", BindingFlags.Public | BindingFlags.Instance);
                    if (getName != null)
                    {
                        var nameValue = getName.Invoke(opponent, null);
                        name = nameValue as string;
                    }
                }
                catch
                {
                    continue;
                }
            }

            if (!string.IsNullOrWhiteSpace(name))
            {
                result.Add(name.Trim());
            }
        }
    }

    return result;
}

static IReadOnlyList<int> ExtractGameIds(object match)
{
    var result = new List<int>();
    try
    {
        var prop = match.GetType().GetProperty("GameIds");
        if (prop == null) return result;

        var value = prop.GetValue(match);
        if (value == null) return result;

        if (value is IEnumerable<int> intList)
        {
            result.AddRange(intList);
        }
        else if (value is IEnumerable enumerable)
        {
            foreach (var item in enumerable)
            {
                if (item is int id)
                {
                    result.Add(id);
                }
            }
        }
    }
    catch
    {
        // Silently ignore errors
    }
    return result;
}

static IReadOnlyList<MatchSummary> ExtractTournamentMatches(object tournament)
{
    var result = new List<MatchSummary>();
    try
    {
        var prop = tournament.GetType().GetProperty("Matches");
        if (prop == null) return result;

        var value = prop.GetValue(tournament);
        if (value == null) return result;

        if (value is IEnumerable matches)
        {
            foreach (var match in matches)
            {
                if (match == null) continue;

                var id = SafeGet<int>(match, "Id");
                var startTime = SafeGet(match, "StartTime", DateTime.MinValue);
                var gameWins = SafeGet<int>(match, "GameWins");
                var gameLosses = SafeGet<int>(match, "GameLosses");
                var gameTies = SafeGet<int>(match, "GameTies");
                var opponents = ExtractOpponentNames(match);
                var gameIds = ExtractGameIds(match);

                result.Add(new MatchSummary(
                    id,
                    startTime,
                    gameWins,
                    gameLosses,
                    gameTies,
                    opponents,
                    gameIds
                ));
            }
        }
    }
    catch
    {
        // Silently ignore errors
    }
    return result;
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
    // currency read scans the whole frozen collection (seconds, remote) and
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
    // UI thread server-side, so a long currency scan blocks timer reads anyway
    // (measured: a concurrent scan stalls the timer loop entirely). The lock keeps
    // the timer loop responsive instead — it grabs the lock without blocking and
    // reuses cached timers if the (rare, idle-only) currency scan holds it. The
    // currency loop additionally pauses while a timer is active, so in steady state
    // during an event the two never contend.
    using var sdkLock = new SemaphoreSlim(1, 1);
    var cache = new WatchCache();

    // Task.Run so each loop gets its own thread: the SDK reads are synchronous
    // blocking calls, and SemaphoreSlim.WaitAsync completes synchronously on a
    // free lock, so without this the first loop would run inline (through its
    // slow first scan) before the second ever started.
    var currencyTask = Task.Run(
        () => RunCurrencyRefreshLoopAsync(sdkLock, cache, currencyInterval.Value, cts.Token),
        cts.Token);
    var timerTask = Task.Run(
        () => RunChallengeTimerLoopAsync(options, sdkLock, cache, timerInterval.Value, cts.Token),
        cts.Token);

    try
    {
        // If either loop exits (cancellation or fatal error), tear the other down.
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
    JsonSerializerOptions options,
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

        var snapshot = new WatchSnapshot(DateTimeOffset.UtcNow, cache.Timers, cache.Currency, error);
        Console.WriteLine(JsonSerializer.Serialize(snapshot, options));

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
// duration of the (slow) scan; the timer loop keeps emitting meanwhile.
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

    var card = entry.Card;
    if (card != null)
    {
        var isTicket = SafeGet<bool?>(card, "IsTicket", null);
        if (isTicket == true)
        {
            return true;
        }
    }

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
        "history" or "matches" => ExecutionMode.History,
        "all" or "both" => ExecutionMode.All,
        "currency" or "wallet" or "tickets" or "points" => ExecutionMode.Currency,
        "watch" or "monitor" => ExecutionMode.Watch,
        "logfiles" or "logs" => ExecutionMode.LogFiles,
        "username" or "user" or "name" => ExecutionMode.Username,
        "trade" or "trades" => ExecutionMode.Trade,
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
    History,
    All,
    Currency,
    Watch,
    LogFiles,
    Username,
    Trade,
}

enum TradeCommand
{
    Status = 0,
    Accept,
}

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
    // multi-second currency scan would otherwise block fresh timer reads. Pausing
    // gives the timer exclusive, uninterrupted access whenever an event is live.
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

public sealed record MatchSummary(
    int Id,
    DateTime StartTime,
    int GameWins,
    int GameLosses,
    int GameTies,
    IReadOnlyList<string> Opponents,
    IReadOnlyList<int> GameIds
);

public sealed record HistoryEntry(
    string Kind,
    int Id,
    DateTime StartTime,
    IReadOnlyList<string> Opponents,
    int? GameWins,
    int? GameLosses,
    int? GameTies,
    IReadOnlyList<int>? GameIds,
    IReadOnlyList<MatchSummary>? Matches,
    int? MatchWins,
    int? MatchLosses
);

public sealed record HistorySnapshot(
    bool HistoryLoaded,
    IReadOnlyList<HistoryEntry> Items,
    string? Error
);

public sealed record LogFilesSnapshot(
    IReadOnlyList<string> Files,
    string? Error
);

public sealed record UsernameSnapshot(
    string? Username,
    string? Error
);

public sealed record BridgePayload(
    DateTimeOffset Timestamp,
    string Mode,
    CollectionSnapshot? Collection,
    HistorySnapshot? History,
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
