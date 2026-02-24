from unittest.mock import patch

import pytest

from utils.perf import timed


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
