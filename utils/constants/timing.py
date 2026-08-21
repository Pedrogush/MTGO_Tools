"""Time constants and cache aging defaults."""

ONE_HOUR_SECONDS = 60 * 60
ONE_DAY_SECONDS = 24 * 60 * 60

# Collection inventory refresh settings
COLLECTION_CACHE_MAX_AGE_SECONDS = ONE_HOUR_SECONDS

# Metagame scraping cache TTL
METAGAME_CACHE_TTL_SECONDS = ONE_HOUR_SECONDS

# Card image bulk data refresh thresholds
DEFAULT_BULK_DATA_MAX_AGE_DAYS = 30
BULK_DATA_CACHE_FRESHNESS_SECONDS = DEFAULT_BULK_DATA_MAX_AGE_DAYS * ONE_DAY_SECONDS

# How old the on-disk bulk file has to be before startup will replace it with a
# newer one Scryfall has published. Scryfall re-publishes ``default-cards``
# daily and the file is ~120 MB, so refreshing on every publish would cost a
# download a day for card data that changes meaningfully only when a set
# arrives; refusing to refresh at all leaves a new set invisible for as long as
# the install lives (that is how The Hobbit went missing, issue #986
# follow-up). Three days bounds the bandwidth and still picks up a release
# within the week it lands.
BULK_DATA_REFRESH_INTERVAL_SECONDS = 3 * ONE_DAY_SECONDS

BULK_CACHE_MIN_AGE_DAYS = 1
BULK_CACHE_MAX_AGE_DAYS = 365


# MTGO bridge and background fetch timing
MTGO_BRIDGE_USERNAME_TIMEOUT_SECONDS = 5.0
MTGO_BRIDGE_SHUTDOWN_TIMEOUT_SECONDS = 10.0
MTGO_STATUS_POLL_SECONDS = 30
MTGO_STATUS_MAX_FAILURES = 10

# Collection bridge fetch timing
COLLECTION_BRIDGE_TIMEOUT_SECONDS = 60.0

# External HTTP request timeouts
MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS = 30
# Per-archetype GET in the bulk metagame stats scrape. This runs N times in a
# bounded ThreadPoolExecutor (MTGGOLDFISH_STATS_MAX_WORKERS) and is a best-effort
# daily aggregate, so it uses a tighter (connect, read) split via curl_cffi: a
# short connect timeout fails fast on a dead/firewalled host instead of letting
# one hung archetype ride the full 30s and stall its whole wave (and the
# Metagame Analysis spinner). The single user-initiated deck download keeps the
# longer MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS.
MTGGOLDFISH_STATS_CONNECT_TIMEOUT_SECONDS = 5
MTGGOLDFISH_STATS_READ_TIMEOUT_SECONDS = 10
OPPONENT_TRACKER_REQUEST_TIMEOUT_SECONDS = 30

# Opponent tracker timers
OPPONENT_TRACKER_CACHE_TTL_SECONDS = 60 * 30
OPPONENT_TRACKER_POLL_INTERVAL_MS = 2000
OPPONENT_TRACKER_CONFIG_SAVE_DELAY_MS = 200  # debounce delay before persisting window config
OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS = 1.0  # max wait for radar worker on close

# MTGGoldfish cache ages
MTGGOLDFISH_STALE_CACHE_DAYS = 7
MTGGOLDFISH_STALE_CACHE_SECONDS = ONE_DAY_SECONDS * MTGGOLDFISH_STALE_CACHE_DAYS

# MTGGoldfish archetype stats — lookback window for daily result counts
MTGGOLDFISH_STATS_LOOKBACK_DAYS = 7

# MTGGoldfish archetype stats — max concurrent per-archetype deck fetches.
# Bounds the ThreadPoolExecutor that parallelizes the otherwise-serial N+1
# per-archetype HTTP GETs when building the metagame stats cache.
MTGGOLDFISH_STATS_MAX_WORKERS = 16

BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS = 2

# Remote snapshot client — freshness and request timeouts
REMOTE_SNAPSHOT_MAX_AGE_SECONDS = 2 * ONE_HOUR_SECONDS  # re-download if manifest is older than this
REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS = 30

# Bundle snapshot — revalidate bundle if stamp is older than this.
# Set to the real upstream regeneration cadence: a stale stamp triggers a
# *conditional* request (If-None-Match / If-Modified-Since), so an unchanged
# bundle returns 304 and skips the multi-MB download + merge entirely. The TTL
# only bounds how often that cheap revalidation HEAD/GET round-trip happens.
REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS = 6 * ONE_HOUR_SECONDS

# In-app update check (issue #142) — how often the app asks the GitHub Releases
# API whether a newer version has shipped. Deliberately coarse: releases land at
# most a few times a week, the answer is a passive status-bar note nobody is
# waiting on, and the unauthenticated GitHub API budget is 60 requests/hour per
# IP — which a user behind a shared/NAT'd address shares with everything else on
# it. Once a day keeps a ten-launches-a-day user at one request.
UPDATE_CHECK_INTERVAL_SECONDS = ONE_DAY_SECONDS
UPDATE_CHECK_REQUEST_TIMEOUT_SECONDS = 10

# SQLite cache settings
SQLITE_CONNECTION_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000

# Card data download timing
ATOMIC_DATA_HEAD_TIMEOUT_SECONDS = 5
ATOMIC_DATA_DOWNLOAD_TIMEOUT_SECONDS = 300
# Skip the remote HEAD on warm starts unless the cache metadata is older than this.
ATOMIC_DATA_HEAD_TTL_SECONDS = ONE_DAY_SECONDS

# Deck Builder Panel — search debounce
BUILDER_SEARCH_DEBOUNCE_MS = 300  # milliseconds to wait after last filter change before searching

# Scryfall API rate limiting. Scryfall asks clients to keep API traffic to
# ~10 requests/second (a 50-100 ms gap) and to honor Retry-After on 429. The
# image pipeline runs up to 10 concurrent workers, and on a cold start (before
# the local bulk index exists) every card is a per-card /cards/named API call,
# so without a shared throttle those workers trip the limiter within seconds.
# All API requests across every session/worker share one budget via this gap.
SCRYFALL_API_MIN_INTERVAL_SECONDS = 0.1  # min gap between Scryfall *API* requests (≈10/s)
SCRYFALL_API_MAX_429_RETRIES = 4  # times to honor Retry-After before giving up on a 429
SCRYFALL_API_RETRY_AFTER_FALLBACK_SECONDS = 1.0  # wait when a 429 omits Retry-After
SCRYFALL_API_RETRY_AFTER_MAX_SECONDS = 10.0  # clamp so a hostile Retry-After can't stall a worker
# Cold-start metadata resolution is batched: when the local bulk index isn't
# available yet (fresh install, before bulk_data.json finishes downloading),
# resolution misses are collected for this debounce window and resolved in a
# single /cards/collection POST instead of one /cards/named GET per card. A lone
# miss in the window still uses the per-card /cards/named endpoint.
IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS = 0.5  # collect the active fetch burst before firing
SCRYFALL_COLLECTION_MAX_IDENTIFIERS = 75  # Scryfall's hard cap per /cards/collection request

# Scryfall bulk image downloader — download configuration
SCRYFALL_REQUEST_TIMEOUT_SECONDS = 30  # timeout for individual Scryfall API/image requests
SCRYFALL_BULK_STREAM_TIMEOUT_SECONDS = 120  # timeout for streaming the bulk data download
SCRYFALL_MAX_DOWNLOAD_WORKERS = 10  # concurrent image download threads
SCRYFALL_DOWNLOAD_CHUNK_SIZE = 8192  # byte chunk size when streaming downloaded images
SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL = 100  # invoke progress callback every N completed cards

# Startup cache warm-up — lazy background pre-fetch of decklists and card images.
# The warm-up threads idle for this long after startup before doing any work, so
# they never compete with the initial archetype/deck/card-data loads for the
# network or CPU during the first few seconds of the session.
CACHE_WARMUP_START_DELAY_SECONDS = 5.0
# Pause between fetches during the *fast* initial warm-up pass (the first deck
# of every archetype plus the top decklists of every format). Effectively
# back-to-back — network latency paces it — so the data a user is most likely
# to open is local within the first minute.
CACHE_WARMUP_FAST_THROTTLE_SECONDS = 0.0
# Pause between fetches during the *slow* deep pass (every remaining decklist).
# Deliberately large so the exhaustive backfill trickles in the background
# without competing for the network. The stop event is waited on during the
# pause so shutdown interrupts the warm-up immediately.
CACHE_WARMUP_SLOW_THROTTLE_SECONDS = 20.0
# Max seconds to wait for each warm-up thread to join on shutdown.
CACHE_WARMUP_JOIN_TIMEOUT_SECONDS = 2.0
# Number of "top" decklists per format the decklist warmer hydrates first (the
# headline list of each of the top N archetypes) before deep-loading a format.
CACHE_WARMUP_TOP_DECKS_PER_FORMAT = 6
# Hard ceiling on how many decklists the *slow deep pass* (Phases 2 + 3) hydrates
# in a session. Without it the deep pass walks every list of every format at the
# 20s slow throttle — tens of hours of background scraping that never completes,
# so the process never goes idle. Capping it lets the warmer finish and quiesce.
CACHE_WARMUP_DEEP_PASS_MAX_DECKS = 150
# Emit a progress log line every N hydrated decklists so the warm-up is visible
# without logging every individual fetch.
CACHE_WARMUP_PROGRESS_INTERVAL = 50

# Predictive card-image prefetch (issue #951) — UI surfaces submit the cards a
# user is likely to look at next (loaded deck zones, top visible research
# decks, the visible window of the card search) and a background worker feeds
# them through the shared download queue in bounded batches.
IMAGE_PREFETCH_BATCH_LIMIT = 100  # max images enqueued per prefetch batch
IMAGE_PREFETCH_IDLE_WAIT_SECONDS = 0.5  # condition wait timeout when no batches are queued
IMAGE_PREFETCH_STOP_TIMEOUT_SECONDS = 2.0  # max seconds to wait for worker join on stop
# Background-tier prefetch batches idle this long after startup (mirrors
# CACHE_WARMUP_START_DELAY_SECONDS) so speculative downloads never compete
# with the initial archetype/deck/card-data loads or the first paint.
# User-driven batches (the selected deck, visible research decks) bypass the
# delay — those are the images the user is waiting on right now.
IMAGE_PREFETCH_START_DELAY_SECONDS = 3.0
# Downloaded-image UI refreshes are coalesced: completed downloads accumulate
# and the deck tables repaint at most once per interval, so a mass download
# (empty cache + warm-up) can never flood the UI event loop.
IMAGE_REFRESH_COALESCE_MS = 250
# Card search results: prefetch everything visible plus this many rows past the
# bottom, so a small scroll still hits already-local images…
SEARCH_PREFETCH_LOOKAHEAD_CARDS = 20
# …and always at least this many rows even when fewer are visible.
SEARCH_PREFETCH_MIN_CARDS = 30
SEARCH_PREFETCH_DEBOUNCE_MS = 250  # settle time after scroll/search before prefetching
# Deck research: prefetch the card images of this many decks from the top of
# the (filtered) results list — the decks the user is most likely to click.
RESEARCH_PREFETCH_DECK_COUNT = 3

# Card image download queue — retry and timing configuration
IMAGE_DOWNLOAD_QUEUE_STOP_TIMEOUT_SECONDS = (
    2.0  # max seconds to wait for queue thread to join on stop
)
IMAGE_DOWNLOAD_QUEUE_IDLE_WAIT_SECONDS = (
    0.5  # condition wait timeout when queue is empty or at capacity
)
IMAGE_DOWNLOAD_MAX_RETRIES = 5  # max retry attempts before giving up on a card image download
IMAGE_DOWNLOAD_INITIAL_BACKOFF_SECONDS = 0.5  # initial backoff delay before first retry
IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS = (
    1.5  # elapsed time above which a "successful" download is treated as failed
)
# Self-heal guard: non-permanent download failures (e.g. a transient error, or a
# cold-start miss before the local bulk index existed) are remembered and
# re-attempted once the index becomes available — the moment those retries can
# actually succeed. Bounds how many are held so a long offline stretch can't grow
# the set without limit.
IMAGE_DEFERRED_RETRY_MAX = 5000
