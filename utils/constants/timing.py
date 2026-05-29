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

# Scryfall bulk image downloader — download configuration
SCRYFALL_REQUEST_TIMEOUT_SECONDS = 30  # timeout for individual Scryfall API/image requests
SCRYFALL_BULK_STREAM_TIMEOUT_SECONDS = 120  # timeout for streaming the bulk data download
SCRYFALL_MAX_DOWNLOAD_WORKERS = 10  # concurrent image download threads
SCRYFALL_DOWNLOAD_CHUNK_SIZE = 8192  # byte chunk size when streaming downloaded images
SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL = 100  # invoke progress callback every N completed cards

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
