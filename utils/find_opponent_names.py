try:
    import pygetwindow
except NotImplementedError:

    class _Stub:
        def getAllTitles(self) -> list[str]:  # pragma: no cover
            return []

    pygetwindow = _Stub()  # type: ignore[assignment]


def find_opponent_names():
    window_names: list[str] = pygetwindow.getAllTitles()
    opponents = []
    for name in window_names:
        if "vs." in name:
            opponents.append(name.split("vs.")[-1].strip())
    return opponents
