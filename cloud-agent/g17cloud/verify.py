"""Deployment verification helpers for the G17 cloud agent.

Stdlib-only, side-effect free module so it can be imported from guards,
maintenance and pipeline code without pulling in extra dependencies.
"""

from __future__ import annotations

import math

__all__ = ['VerifyError', 'stale_deployment']


class VerifyError(Exception):
    """Raised when a verification input is invalid or a check cannot run."""


def _as_seconds(value, name):
    """Normalise a duration argument to a finite, non-negative float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VerifyError(
            '{0} must be a real number, got {1}'.format(name, type(value).__name__)
        )
    seconds = float(value)
    if not math.isfinite(seconds):
        raise VerifyError('{0} must be finite, got {1!r}'.format(name, value))
    if seconds < 0:
        raise VerifyError('{0} must be >= 0, got {1}'.format(name, seconds))
    return seconds


def stale_deployment(uptime_sec, age_sec):
    """Return True when the running process predates the newest deployment.

    Args:
        uptime_sec: how long the current process has been running, in seconds.
        age_sec: how long ago the deployment artifact was published, in seconds.

    Returns:
        True if ``uptime_sec > age_sec`` (the process started before the latest
        deployment, so it is still serving stale code), otherwise False.

    Raises:
        VerifyError: if either argument is not a finite, non-negative number.
    """
    uptime = _as_seconds(uptime_sec, 'uptime_sec')
    age = _as_seconds(age_sec, 'age_sec')
    return uptime > age
