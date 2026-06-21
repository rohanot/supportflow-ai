from __future__ import annotations

import hashlib

from jinja2 import Environment, StrictUndefined


_ENV = Environment(undefined=StrictUndefined, autoescape=False)


def render_template(template: str, **inputs: object) -> str:
    return _ENV.from_string(template).render(**inputs)


def hash_prompt(rendered_prompt: str) -> str:
    return hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()

