"""Decode the Nuxt 3 ``__NUXT_DATA__`` payload (devalue format) embedded in
a Jiji page into plain Python objects."""
from __future__ import annotations

import json
import re
from typing import Any

_PAYLOAD_RE = re.compile(
    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef"}


def decode_nuxt_data(html: str) -> Any | None:
    m = _PAYLOAD_RE.search(html)
    if not m:
        return None
    arr = json.loads(m.group(1))
    memo: dict[int, Any] = {}

    def res(i: int) -> Any:
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _WRAPPERS:
                memo[i] = res(v[1]) if len(v) > 1 else None
                return memo[i]
            if v and isinstance(v[0], str) and v[0] in {
                    "EmptyRef", "EmptyShallowRef", "Set", "Map", "Date",
                    "null", "undefined", "BigInt", "Object", "Error", "NuxtError"}:
                memo[i] = None
                return None
            out: list = []
            memo[i] = out
            out.extend(res(x) if isinstance(x, int) and not isinstance(x, bool) else x for x in v)
            return out
        if isinstance(v, dict):
            d: dict = {}
            memo[i] = d
            for k, x in v.items():
                d[k] = res(x) if isinstance(x, int) and not isinstance(x, bool) else x
            return d
        memo[i] = v
        return v

    return res(0)


def find_advert(root: Any) -> dict | None:
    """The listing object: first dict having both ``attrs`` and ``guid``."""
    stack = [root]
    seen: set[int] = set()
    while stack:
        o = stack.pop()
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, dict):
            if "attrs" in o and "guid" in o and "category_slug" in o:
                return o
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return None
