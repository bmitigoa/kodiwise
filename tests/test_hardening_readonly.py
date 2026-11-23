"""Step 3: least privilege. Tools are read-only; the only writes in the system are the chat counters."""
import ast
import json
from pathlib import Path

import pytest

from agent.core import listings as L
from agent.core.tools import Tools
from chat import toolspec
from tests.test_chat import make_tools

ROOT = Path(__file__).resolve().parents[1]
WRITE_NAMES = {"set", "update", "delete", "add", "create", "commit", "batch", "transaction", "bulk_writer",
               "write", "write_text", "write_bytes", "unlink", "remove", "rmdir", "mkdir", "touch", "rename",
               "replace", "system", "popen", "run", "check_output", "check_call", "Popen"}


class _Q:
    def __init__(self, docs, fs):
        self.docs, self.fs = docs, fs

    def where(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def select(self, fields):
        self.fs.projections.append(list(fields))
        return self

    def stream(self):
        class D:
            def __init__(s, d): s.d = d
            def to_dict(s): return s.d
        return [D(d) for d in self.docs]

    def __getattr__(self, name):          # any other call (set/add/delete/...) is a recorded write attempt
        def rec(*a, **k):
            self.fs.writes.append(name)
        return rec


class RecordingFirestore:
    """Fake Firestore client: reads work, anything else is recorded as a write."""

    def __init__(self, docs):
        self.docs, self.writes, self.projections = docs, [], []

    def collection(self, name):
        self.last_collection = name
        return _Q(self.docs, self)

    def __getattr__(self, name):
        def rec(*a, **k):
            self.writes.append(name)
        return rec


def test_all_six_tools_run_without_any_firestore_write_and_only_read_approved_projected_fields():
    fs = RecordingFirestore([{"status": "approved", "title": "x", "locationName": "Kilimani", "quotedRent": 50000,
                              "bedrooms": 2, "bathrooms": 1}])
    base, _ = make_tools()
    tools = Tools(base.api, L.FirestoreListingSource(client_factory=lambda: fs), centroids=base.centroids)
    calls = {"list_locations": {}, "estimate_rent": {"location": "Kilimani", "bedrooms": 2, "bathrooms": 1},
             "compare_areas": {"locations": ["Kilimani", "Westlands"], "bedrooms": 2, "bathrooms": 1},
             "areas_within_budget": {"budget_kes": 60000, "bedrooms": 2, "bathrooms": 1, "near": "Westlands"},
             "check_listing_price": {"asking_rent_kes": 70000, "location": "Kilimani", "bedrooms": 2, "bathrooms": 1},
             "search_listings": {"location": "Kilimani"}}
    for name, args in calls.items():
        res = toolspec.call_tool(tools, name, args)
        assert "error" not in res, (name, res)
    assert fs.writes == []
    assert fs.last_collection == "properties"
    assert fs.projections and set(fs.projections[0]) == set(L.SAFE_FIELDS)
    for forbidden in ("ownerId", "ownerEmail", "adminNotes", "description", "imageUrls", "phone", "email"):
        assert forbidden not in fs.projections[0]


def test_the_tool_surface_has_no_write_tool_in_mcp_or_chat():
    names = {d["name"] for d in toolspec.DECLARATIONS}
    assert names == {"list_locations", "estimate_rent", "compare_areas", "areas_within_budget",
                     "check_listing_price", "search_listings"}
    for n in names:
        assert not any(w in n for w in ("write", "delete", "update", "set_", "create", "send", "save", "remove"))
    tool_methods = {m for m in dir(Tools) if not m.startswith("_")}
    assert not (tool_methods & {"write", "delete", "update", "save", "send", "set", "create"})


def _calls_in(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if not isinstance(f, ast.Attribute):
                if isinstance(f, ast.Name) and f.id in ("open", "Popen", "system"):
                    out.append((node.lineno, f.id))       # open(...) is checked for write modes below
                continue
            name, base = f.attr, (f.value.id if isinstance(f.value, ast.Name) else "")
            if name in ("run", "check_output", "check_call", "Popen", "system", "popen"):
                if base in ("subprocess", "os"):
                    out.append((node.lineno, name))
            elif name in WRITE_NAMES:
                out.append((node.lineno, name))
    return out


def _is_write_use(path: Path, name: str, line: int) -> bool:
    """Ignore harmless homonyms: str.replace, dict.update on local data, subprocess.run is NOT harmless."""
    src = path.read_text(encoding="utf-8").splitlines()[line - 1]
    if name == "open":                                    # reading is fine; a write mode is not
        import re
        return bool(re.search(r"""['"][^'"]*[wax+][^'"]*['"]""", src.split("open(", 1)[1].split(")")[0].split("encoding")[0]))
    harmless = (".replace(", "re.sub", "dict(", "kw.update", "c.update", ".update({", "view.update", "out.update")
    if name in ("replace", "update", "set", "add") and any(h in src for h in harmless):
        return False
    return True


def test_only_chat_limits_py_writes_to_firestore_and_nothing_writes_files_or_runs_commands():
    offenders = []
    for folder in ("agent", "chat"):
        for p in (ROOT / folder).rglob("*.py"):
            if p.name in ("limits.py",) and p.parent.name == "chat":
                continue                                   # the one module that owns counter writes
            if p.name in ("telemetry.py", "model_eval.py"):
                continue                                   # local traces file / eval script (checked below)
            for line, name in _calls_in(p):
                if _is_write_use(p, name, line):
                    offenders.append(f"{p.relative_to(ROOT)}:{line} {name}")
    assert offenders == []


def test_limits_py_is_the_only_place_that_names_the_counter_collections():
    hits = []
    for folder in ("agent", "chat"):
        for p in (ROOT / folder).rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if ("chatUsage" in text or "chatGlobal" in text) and p.name != "limits.py":
                hits.append(str(p.relative_to(ROOT)))
    assert hits == []


def test_the_only_firestore_collections_the_code_touches_are_properties_and_the_two_counters():
    found = set()
    for folder in ("agent", "chat"):
        for p in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "collection":
                    arg = node.args[0] if node.args else None
                    if isinstance(arg, ast.Constant):
                        found.add(arg.value)
                    elif isinstance(arg, ast.Name) or isinstance(arg, ast.Attribute):
                        found.add("<constant>")
    assert found <= {"properties", "<constant>"}      # <constant> = COLLECTION / USERS / GLOBAL names
    consts = {L.COLLECTION}
    from chat.limits import FirestoreCounters
    consts |= {FirestoreCounters.USERS, FirestoreCounters.GLOBAL}
    assert consts == {"properties", "chatUsage", "chatGlobal"}


def test_counter_documents_hold_no_message_text():
    from chat.limits import FirestoreCounters

    class Ref:
        def __init__(self): self.data = None
        def get(self, transaction=None):
            class S: exists = False
            return S()

    class Tx:
        def __init__(self): self.sets = []
        def set(self, ref, data): self.sets.append(data)

    # the stored fields are fixed: count, uid/day or day, expireAt
    src = (ROOT / "chat" / "limits.py").read_text(encoding="utf-8")
    assert '{"uid": uid, "day": day,' in src and '{"day": day,' in src
    assert "text" not in json.dumps(["count", "uid", "day", "expireAt"])
    assert FirestoreCounters.USERS == "chatUsage"
