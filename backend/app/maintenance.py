"""Process-local maintenance switch, toggled from the admin dashboard.

In-memory on purpose: instant to flip, no DB round-trip, and it resets to off
on restart or deploy, so a deploy returns the site to live automatically and
the site can never get stuck in maintenance. Single uvicorn worker in prod, so
one process holds the truth.
"""
_on = False


def is_on() -> bool:
    return _on


def set_on(value: bool) -> None:
    global _on
    _on = bool(value)
