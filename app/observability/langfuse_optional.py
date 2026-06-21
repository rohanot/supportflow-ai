from __future__ import annotations


def is_langfuse_enabled() -> bool:
    return False


def send_langfuse_event(*_: object, **__: object) -> None:
    return None

