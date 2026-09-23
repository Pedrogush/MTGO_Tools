# Testing guidelines

How we write tests for the MTGO Tools wxPython app. The goal of these rules is a
suite that is **fast, deterministic, and actually exercises production behavior** —
not one that re-asserts the shape of its own mocks.

If you're adding or reviewing tests, read §1–§3, and §7 before you point a test at
anything on disk. The rest is reference.

---

## 1. Default to real objects; this is a monolith

This app is an in-process monolith. Controllers, services, repositories, parsers,
and utilities are fast, deterministic, and side-effect-free to construct. **Use the
real ones.** A test that wires up a real `DeckService` against a real
`DeckRepository` pointed at a temp dir proves the system works; a test that wires up
`FakeDeckService` proves only that the fake behaves.

The preference order, strongest first:

> **real implementation → fake (only if real is impractical) → stub/mock (last resort)**

This is the guidance in *Software Engineering at Google* (Winters, Manshreck &
Wright, O'Reilly 2020, Ch. 13 "Test Doubles"): prefer realism over isolation,
because mock-heavy tests "verify how the code is implemented rather than what it
does" and become **change-detector tests** that break on every refactor without
catching real bugs. Martin Fowler frames the same split as classical vs. mockist
TDD in ["Mocks Aren't Stubs"](https://martinfowler.com/articles/mocksArentStubs.html);
the classical (real-collaborator) style is what we follow.

**Do not mock internal app components** — repositories, services, caches, parsers,
or domain models. If a test needs data, feed a real object real fixture data (see §3).

## 2. Mock only what you don't own and can't control: network & scraping

The legitimate reasons to use a test double are dependencies that are **slow,
nondeterministic, unavailable in CI, or have external side effects** (Meszaros,
*xUnit Test Patterns*, 2007). In this codebase that means exactly one category:

- **Outbound network / scraping** — `requests`/`urllib`, MTGOgoldfish scrapers,
  Scryfall bulk data, remote snapshot fetches, the MTGO bridge.

Prefer to fake these **at a seam you own** rather than monkeypatching a third-party
symbol directly. "Don't mock what you don't own" — Freeman & Pryce, *Growing
Object-Oriented Software, Guided by Tests* (2009): wrap the external call behind a
small adapter and fake the adapter, or replay recorded responses (VCR-style
cassettes / saved JSON fixtures). Patching `repositories.scrapers.mtggoldfish.requests.get`
is acceptable; patching an internal method of the unit under test is not.

| Dependency | Treatment | Why |
|---|---|---|
| In-process app code (repos, services, parsers, models) | **Real objects + fixture data** | SE@Google "prefer real"; Fowler classical TDD |
| External I/O you don't own (HTTP scraping, MTGO bridge, Scryfall) | **Fake at a seam you own** (adapter / recorded responses) | Freeman & Pryce "don't mock what you don't own" |
| `wx` GUI framework | **Humble Object — keep logic wx-free; touch wx only at the unavoidable edge** | Meszaros & Fowler (Humble Object); MS MVVM |

## 3. Fixtures = real behavior on a temp surface

Using `tmp_path` with real file I/O and committed sample data (e.g. a small
`scryfall_cards.json`) is **not a mock** — it's the real code path on a disposable
surface. It's fast, deterministic, and the gold standard for the broad base of the
test pyramid (Mike Cohn, *Succeeding with Agile*; Fowler,
["TestPyramid"](https://martinfowler.com/bliki/TestPyramid.html)).

- Redirect file/cache constants to `tmp_path` via `monkeypatch.setattr` — this is
  path relocation of real I/O, and is encouraged.
- **Except when the constant is consumed as a constructor default** (e.g.
  `def __init__(self, db_path: Path = DECK_CACHE_DB)`): that default is bound at
  import time, so `monkeypatch.setattr` on the constant cannot reach it and the
  code keeps writing to the real path. Give the collaborator a seam — a
  constructor parameter defaulting to the constant — and point the seam at
  `tmp_path` instead.
- Keep sample fixtures small and checked in under `tests/fixtures/`.
- Parse results back and assert on real values; don't assert "no exception raised"
  and call it coverage.

## 4. Testing wx / GUI code (the hard part)

`wx` is the classic "hard to test" dependency, and it has a sharp CI gotcha
(see §5). The right answer is the **Humble Object** pattern (Meszaros; Fowler):
**push logic out of the GUI class into a plain object you can test without wx,**
leaving the widget so thin it needs no test. Microsoft's MVVM guidance for WPF/.NET
encodes the same separation (testable ViewModel, inert View).

Concretely:

- Don't thread `wx.CallAfter`, `wx.MessageBox`, dialogs, etc. through business logic.
  Inject a dispatcher/notifier (defaulting to the wx call in production, a direct
  call in tests) so there is nothing wx-shaped to mock.
- When you must touch wx in a test, stub the minimal surface — and **stub it
  whether or not wx imports** (see §5). Fake widgets (`_FakePanel`, `_FakeList`,
  …) standing in for the View are acceptable; faking a repository behind the View
  is not (§1).

### The `wx.CallAfter` / "No wx.App created yet" trap

`import wx` **succeeds on the Windows CI runner** but there is **no `wx.App`** in the
test process, so a real `wx.CallAfter(...)` raises `AssertionError: No wx.App created
yet`. A test that assumes "wx is absent in tests" passes locally in WSL (where wx
truly is absent) and then **fails only on CI**. Stub `CallAfter` to run synchronously
whenever wx is importable:

```python
@pytest.fixture(autouse=True)
def _synchronous_call_after(monkeypatch):
    try:
        import wx
    except ImportError:
        return  # off-Windows: production fallback already runs synchronously
    monkeypatch.setattr(wx, "CallAfter", lambda func, *a, **k: func(*a, **k))
```

### One window per module (`shared_frame`)

Building an `AppFrame` costs about 1.2s, which was most of the UI suite's run
time when every test built its own. `tests/ui/conftest.py` offers one window per
**module** instead:

- **`shared_frame`** — the module's `AppFrame`, reset before each test by
  `SharedAppFrame.reset()`: the test doubles installed on the frame or the
  controller are removed, the load flags and load-dedup memory go back to their
  construction values, the research format and its filters and the builder's
  filters are cleared, the loaded deck (current deck, its text, the deck list,
  the zones) is emptied, the archetype list and its selection go back to empty,
  the window returns to its own size, both card views return to their starting
  mode, and every `wx.Timer` in the window — including the ones on panels, which
  is nearly all of them — is stopped. Use it for anything that needs *a* main
  window.
- **`deck_selector_factory`** — a newly built window. Use it when the test is
  about construction, startup, session restore, persistence across windows, or
  anything that reads a file whose path came from this test's `ui_environment`
  (the shared window's paths are the module's). `test_notes_persist_across_frames`
  and `test_the_default_folder_option_persists_and_clears` are the shape of it.

Both fixtures build their window on an `AppController()` of their own; neither
touches the application's controller singleton, and `tests/test_ui_fixture_guards.py`
fails any UI file that names `get_deck_selector_controller`. Mixing the two
fixtures in one module is therefore fine.

Scope is the module, never the session, so a window a test leaves in a state the
reset does not cover can only affect its own file. If your test needs a
precondition the reset does not give it, set it in the test (or in the file's own
fixture) — that is ordinary test setup.

**Check order independence** when you add to a shared-window file:

```bash
pytest tests/ui/test_whatever.py -p randomly
```

`pytest-randomly` is pinned in `requirements-dev.txt` but blocked by default
(`-p no:randomly` in `pyproject.toml`), because a gating run has to be
reproducible from the command that produced it; `-p randomly` turns it back on
for the run you type. It shuffles within a module and never interleaves two of
them, which is the right scope here — one window serves one module. The seed is
printed in the header, and `--randomly-seed=N` replays an order exactly.

CI runs the same thing weekly and on demand as the `tests-ui-shuffled` job. It
is deliberately not a PR gate: shuffled UI failures are real but intermittent,
and an intermittent required check is one people rerun instead of read. The part
of the contract that *is* deterministic — that the reset actually puts the
window back — is pinned on every PR by `tests/ui/test_shared_frame_reset.py`,
whose tests each assert the window is clean and then deliberately wreck it, so
the file cannot pass by being run in a lucky order.

### Waiting for the UI

Never pump the event queue a fixed number of times, and never `sleep` a fixed
slice of time: both are guesses about how much a machine gets done per pass, and
both are how `test_match_history_filters` became flaky. Wait on the condition
with `wait_until(wx_app, lambda: ...)` (`tests/ui/conftest.py`), which pumps
until the condition holds and fails with a message if it never does. A generous
timeout costs nothing when the condition is met.

## 5. Running the tests (WSL vs Windows) — CI is the source of truth

`wx` is **not importable in the WSL dev environment**. Off-Windows runs therefore
skip or fall back on wx paths, so a green run in WSL does **not** prove the wx paths
pass. Validate on Windows before trusting a wx-touching change:

```bash
# from WSL, against a checkout on the C: drive:
cmd.exe /c "cd /d C:\Claude\MTGO_Tools && .venv\Scripts\python.exe -m pytest -q"
```

CI runs the suite as two jobs: the non-UI tests across the runner's cores with
`pytest-xdist`, and the UI tests serially in a job of their own. Locally,
`python scripts/run_tests_fast.py` does the same split in one command; plain
`pytest` still runs everything serially. A non-UI test therefore has to be
safe to run beside any other — no fixed ports, no shared temp-file names outside
`tmp_path`, no reliance on another test having run first.

Tests, the Windows installer build, .NET build, type checking, and security scans
are validated by **CI**, which is the authoritative gate for anything that can't run
under WSL. Never isolate or delete tests just to make them importable off-Windows —
fix the seam (§4) instead.

## 6. What a good test asserts

- **Exercises the real branches** — error handlers, edge cases, and every public
  entry point of the unit, not just the happy path.
- **Asserts on values**, not just absence of exceptions.
- **Behavior, not interactions** — avoid asserting "method X was called"; assert the
  observable result. Interaction assertions couple the test to the implementation
  (Fowler, "Mocks Aren't Stubs").
- **No redundancy** — if another test already covers a path, don't restate it.

## 7. Data isolation: the suite runs on top of the user's real data

Read this before a test touches the filesystem. It is the one hazard in this
repo that has bitten us repeatedly, and the reason a test run can fail for
something that happened outside the test.

### Why the hazard exists

Run from source, the app does not keep its data in a per-user application
directory. `utils/constants/paths` resolves the base data dir by walking up from
the working directory to the nearest `.git` marker and taking that checkout's
root, so `config/`, `cache/`, `logs/` and `data/` sit **inside the checkout you
are working in**, and `decks/` is `~/Documents/mtgo_decks`, which is shared by
everything on the machine. A test that reaches a real path therefore does not
write to a sandbox — it writes the developer's own settings, caches and saved
decks, and the damage is already done by the time anything notices.

Worse, a **worktree does not get its own copy**. For a linked worktree the same
resolution follows the `.git` pointer file back to the *primary* checkout, so a
suite running in `../wt-something` reads and writes the primary checkout's
`config/` and `cache/`. Every worktree on the machine, plus the app itself,
plus every other worktree's suite, are all writing the same directories.

This is not hypothetical. The guard described below was written after
`test_notebook_tabs_fit` overwrote the real `config/deck_selector_settings.json`
and `test_notes_persist_across_frames` cleared the real `deck_notes.json`; it
also caught the radar, card-pool and image caches being created by repositories
constructed with their real default paths.

### How the suite stays out of them

`tests/data_isolation.py` redirects the real paths into a tmp dir. Patching the
constants on `utils.constants` is **not** enough on its own, because three kinds
of reference keep a copy of the real path:

- a name imported at module load — `from utils.constants import NOTES_STORE`, or
  an alias assigned at import time;
- a default argument, which Python evaluates once, when the function is defined
  (the same trap as the constructor-default bullet in §3);
- work a test left running on a thread, which lands *after* the test's patches
  are undone.

`redirect_bound_paths` rewrites the first two in every loaded project module. The
root conftest applies it once for the whole session and deliberately never undoes
it, so late work from a thread a test left running still lands in the session tmp
dir; `tests/ui/conftest.py` layers a per-test redirect on top. Import the module
as `data_isolation`, never `tests.data_isolation` — a second copy would record
the already-patched paths as the "real" ones and the guard would check nothing.

None of this excuses you from §3. The redirect is a net, not a design: point your
collaborator at `tmp_path` through a seam and the net never has to catch anything.

### The two guards

A process-wide `sys.addaudithook` records every real-data path **this process**
opens for writing. Two fixtures use it:

- **Per test (function-scoped).** After each test, the paths the hook recorded
  during it are diffed. If the test wrote real data, that test fails, naming its
  own node id — so `-x` stops on the write rather than long after it, and you get
  the culprit instead of a bisect.
- **Per run (session-scoped).** Every file under the real data dirs is snapshotted
  (size and mtime) before the first test and again after the last. **Any change
  fails the run.**

Attribution decides the *message*, not the verdict. A changed path the audit hook
saw this process write is reported as the suite's own doing. Anything else names
the two remaining possibilities: a subprocess the suite spawned — the hook is
per-process and cannot see a child, and this suite spawns real ones — or another
program writing the shared directories. Both still fail, because by the time the
snapshot is compared the data is already gone either way.

### The opt-out, and what reaching for it means

`MTGO_TOOLS_ALLOW_CONCURRENT_APP=1` is for the run where you *know* there is a
second writer: you have `main.py --automation` open in another window, or another
worktree's suite going. It downgrades **only** the unattributed case to a warning.

It does not launder anything else:

- a write this process made is still a hard failure, opt-out or not;
- `CI` overrides the opt-out — an environment with both set still fails, because
  CI has no second writer to excuse.

So if you set it and the run still fails, the write came from the suite, and you
have a real bug: find the path that escaped the redirect and give it a seam. Set
it per run, from the shell, for the reason above — never export it permanently and
never add it to a config file. The case it downgrades is precisely the one the
guard cannot tell apart from a subprocess the suite spawned, and a subprocess
wiping `config/` is a leak, not a neighbour.

If you would rather the question could not arise, `MTGO_TOOLS_BASE_DATA_DIR`
moves `config/`, `cache/`, `logs/` and `data/` somewhere else for a process that
sets it. It does not move the deck folder, which lives under `~/Documents`.

---

### Sources

- Winters, Manshreck & Wright — *Software Engineering at Google* (O'Reilly, 2020), Ch. 13 "Test Doubles".
- Martin Fowler — ["Mocks Aren't Stubs"](https://martinfowler.com/articles/mocksArentStubs.html) and ["TestPyramid"](https://martinfowler.com/bliki/TestPyramid.html).
- Gerard Meszaros — *xUnit Test Patterns: Refactoring Test Code* (Addison-Wesley, 2007) — Test Double / Test Fixture / Humble Object definitions.
- Freeman & Pryce — *Growing Object-Oriented Software, Guided by Tests* (Addison-Wesley, 2009) — "don't mock what you don't own".
- Mike Cohn — *Succeeding with Agile* (Addison-Wesley, 2009) — the test pyramid.
- Microsoft Learn — WPF/.NET MVVM guidance (separating testable ViewModel from the View).

> These paraphrase the works' documented positions; check the primary texts for exact wording before quoting.
