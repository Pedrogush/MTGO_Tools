from unittest.mock import patch

import pytest

from utils.perf import perf_phase, timed


def test_timed_returns_value():
    @timed
    def f():
        return 42

    assert f() == 42


def test_timed_preserves_qualname():
    @timed
    def my_function():
        pass

    assert my_function.__name__ == "my_function"
    assert "my_function" in my_function.__qualname__


def test_timed_wraps_preserves_docstring():
    @timed
    def f():
        """My docstring."""

    assert f.__doc__ == "My docstring."


def test_timed_calls_inner_exactly_once():
    call_count = 0

    @timed
    def f():
        nonlocal call_count
        call_count += 1

    f()
    assert call_count == 1


def test_timed_propagates_exception():
    @timed
    def f():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        f()


def test_timed_passes_args_and_kwargs():
    @timed
    def f(a, b, c=0):
        return a + b + c

    assert f(1, 2, c=3) == 6


def test_timed_logs_qualname_and_elapsed():
    """logger.debug must be called once with qualname and non-negative elapsed time."""

    @timed
    def my_func():
        return 1

    with patch("utils.perf.logger") as mock_logger:
        my_func()

    mock_logger.debug.assert_called_once()
    call_args = mock_logger.debug.call_args
    template, qualname_arg, elapsed_arg = call_args.args
    assert "my_func" in qualname_arg
    assert isinstance(elapsed_arg, float)
    assert elapsed_arg >= 0.0


def test_timed_does_not_log_on_exception():
    """logger.debug must NOT be called when the wrapped function raises."""

    @timed
    def f():
        raise RuntimeError("fail")

    with patch("utils.perf.logger") as mock_logger:
        with pytest.raises(RuntimeError):
            f()

    mock_logger.debug.assert_not_called()


def test_perf_phase_logs_once_with_name_and_ms():
    """perf_phase must log once at INFO with the PERF template, name, and non-negative ms."""
    with patch("utils.perf.logger") as mock_logger:
        with perf_phase("analyze_deck"):
            pass

    mock_logger.log.assert_called_once()
    call_args = mock_logger.log.call_args
    level_arg, template, ms_arg, name_arg = call_args.args
    assert level_arg == "INFO"
    assert template == "PERF | {:>7.1f} ms | {}"
    assert isinstance(ms_arg, float)
    assert ms_arg >= 0.0
    assert name_arg == "analyze_deck"


def test_perf_phase_forwards_level():
    """The keyword-only level arg must be forwarded to logger.log."""
    with patch("utils.perf.logger") as mock_logger:
        with perf_phase("scrape", level="DEBUG"):
            pass

    mock_logger.log.assert_called_once()
    assert mock_logger.log.call_args.args[0] == "DEBUG"


def test_perf_phase_logs_on_exception():
    """perf_phase logs from its finally block even when the segment raises."""
    with patch("utils.perf.logger") as mock_logger:
        with pytest.raises(ValueError, match="boom"):
            with perf_phase("doomed"):
                raise ValueError("boom")

    mock_logger.log.assert_called_once()
    assert mock_logger.log.call_args.args[3] == "doomed"
