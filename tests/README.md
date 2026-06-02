# Testing guidelines

How we write tests for the MTGO Tools wxPython app. The goal of these rules is a
suite that is **fast, deterministic, and actually exercises production behavior** —
not one that re-asserts the shape of its own mocks.

If you're adding or reviewing tests, read §1–§3. The rest is reference.

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

## 5. Running the tests (WSL vs Windows) — CI is the source of truth

`wx` is **not importable in the WSL dev environment**. Off-Windows runs therefore
skip or fall back on wx paths, so a green run in WSL does **not** prove the wx paths
pass. Validate on Windows before trusting a wx-touching change:

```bash
# from WSL, against a checkout on the C: drive:
cmd.exe /c "cd /d C:\Claude\MTGO_Tools && env\Scripts\python.exe -m pytest -q"
```

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

---

### Sources

- Winters, Manshreck & Wright — *Software Engineering at Google* (O'Reilly, 2020), Ch. 13 "Test Doubles".
- Martin Fowler — ["Mocks Aren't Stubs"](https://martinfowler.com/articles/mocksArentStubs.html) and ["TestPyramid"](https://martinfowler.com/bliki/TestPyramid.html).
- Gerard Meszaros — *xUnit Test Patterns: Refactoring Test Code* (Addison-Wesley, 2007) — Test Double / Test Fixture / Humble Object definitions.
- Freeman & Pryce — *Growing Object-Oriented Software, Guided by Tests* (Addison-Wesley, 2009) — "don't mock what you don't own".
- Mike Cohn — *Succeeding with Agile* (Addison-Wesley, 2009) — the test pyramid.
- Microsoft Learn — WPF/.NET MVVM guidance (separating testable ViewModel from the View).

> These paraphrase the works' documented positions; check the primary texts for exact wording before quoting.
