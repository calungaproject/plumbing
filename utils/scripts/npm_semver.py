"""Minimal npm semver helpers for plumbing-utils (no registry I/O).

Keep in sync with npm-builder/scripts/lookup-npm-tl-compliance (Version,
satisfies, max_satisfying).
"""
from __future__ import print_function

import re

_X = {"x", "X", "*"}


def _cmp_pre_ids(a, b):
    """npm: numeric identifiers compare numerically; others as strings."""
    an = len(a)
    bn = len(b)
    for i in range(min(an, bn)):
        ai, bi = a[i], b[i]
        a_num, b_num = ai.isdigit(), bi.isdigit()
        if a_num and b_num:
            av, bv = int(ai), int(bi)
            if av != bv:
                return (av > bv) - (av < bv)
        elif a_num != b_num:
            return -1 if a_num else 1
        else:
            if ai != bi:
                return (ai > bi) - (ai < bi)
    return (an > bn) - (an < bn)


class Version(object):
    __slots__ = ("major", "minor", "patch", "prerelease")

    def __init__(self, text):
        raw = text.strip()
        if raw.startswith("v") or raw.startswith("V"):
            raw = raw[1:]
        if "+" in raw:
            raw = raw.split("+", 1)[0]
        pre = None
        if "-" in raw:
            core, pre = raw.split("-", 1)
        else:
            core = raw
        parts = core.split(".")
        nums = []
        for part in parts[:3]:
            if part in _X or part == "":
                raise ValueError("not a concrete version: %s" % text)
            nums.append(int(part))
        while len(nums) < 3:
            nums.append(0)
        self.major, self.minor, self.patch = nums
        self.prerelease = tuple(pre.split(".")) if pre else None

    def tuple(self):
        return (self.major, self.minor, self.patch)

    def __str__(self):
        core = "%d.%d.%d" % (self.major, self.minor, self.patch)
        if self.prerelease:
            return core + "-" + ".".join(self.prerelease)
        return core

    def __eq__(self, other):
        return self.tuple() == other.tuple() and self.prerelease == other.prerelease

    def __lt__(self, other):
        if self.tuple() != other.tuple():
            return self.tuple() < other.tuple()
        if self.prerelease is None and other.prerelease is None:
            return False
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True
        return _cmp_pre_ids(self.prerelease, other.prerelease) < 0

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return other < self

    def __ge__(self, other):
        return self == other or self > other


def _parse_partial(text):
    """Return (major, minor, patch, wild_at) where wild_at is 0/1/2/3 (3=exact)."""
    raw = text.strip()
    if raw.startswith("v") or raw.startswith("V"):
        raw = raw[1:]
    if "+" in raw:
        raw = raw.split("+", 1)[0]
    if "-" in raw:
        raw = raw.split("-", 1)[0]
    if raw in _X or raw == "":
        return (0, 0, 0, 0)
    parts = raw.split(".")
    nums = []
    wild_at = 3
    for i, part in enumerate(parts[:3]):
        if part in _X:
            wild_at = i
            break
        nums.append(int(part))
    else:
        wild_at = len(nums)
        if wild_at > 3:
            wild_at = 3
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], wild_at)


def _caret_bounds(ver):
    lower = ver
    if ver.major != 0:
        upper = Version("%d.0.0" % (ver.major + 1))
    elif ver.minor != 0:
        upper = Version("0.%d.0" % (ver.minor + 1))
    else:
        upper = Version("0.0.%d" % (ver.patch + 1))
    return lower, upper


def _tilde_bounds(major, minor, patch, wild_at):
    lower = Version("%d.%d.%d" % (major, minor, patch))
    if wild_at <= 1:
        upper = Version("%d.0.0" % (major + 1))
    else:
        upper = Version("%d.%d.0" % (major, minor + 1))
    return lower, upper


def _split_comparators(clause):
    """Split a single ||-clause into tokens, keeping hyphen ranges together."""
    clause = clause.strip()
    if not clause or clause == "*":
        return ["*"]
    hyphen = re.match(r"^(.+?)\s+-\s+(.+)$", clause)
    if hyphen:
        return [">=" + hyphen.group(1).strip(), "<=" + hyphen.group(2).strip()]
    return clause.split()


def _token_to_bounds(token):
    """Return list of (op, Version) with op in >=, <, <=, >, =, *."""
    token = token.strip()
    if token in ("*", "", "x", "X"):
        return [("*", None)]
    if token.startswith("^"):
        partial = token[1:]
        pre = None
        core = partial
        if "-" in partial.split("+", 1)[0]:
            core, pre_s = partial.split("+", 1)[0].split("-", 1)
            pre = tuple(pre_s.split("."))
        major, minor, patch, wild_at = _parse_partial(core)
        ver = Version("%d.%d.%d" % (major, minor, patch))
        ver.prerelease = pre
        if wild_at == 0:
            return [("*", None)]
        if wild_at == 1:
            return [(">=", Version("%d.0.0" % major)), ("<", Version("%d.0.0" % (major + 1)))]
        lower, upper = _caret_bounds(ver)
        return [(">=", lower), ("<", upper)]
    if token.startswith("~"):
        major, minor, patch, wild_at = _parse_partial(token[1:])
        if wild_at == 0:
            return [("*", None)]
        lower, upper = _tilde_bounds(major, minor, patch, wild_at)
        return [(">=", lower), ("<", upper)]
    m = re.match(r"^(>=|<=|>|<|=)?\s*(.+)$", token)
    if not m:
        raise ValueError("bad range token: %s" % token)
    op = m.group(1) or "="
    rest = m.group(2).strip()
    major, minor, patch, wild_at = _parse_partial(rest)
    if wild_at < 3 and op == "=":
        if wild_at == 0:
            return [("*", None)]
        if wild_at == 1:
            return [
                (">=", Version("%d.0.0" % major)),
                ("<", Version("%d.0.0" % (major + 1))),
            ]
        return [
            (">=", Version("%d.%d.0" % (major, minor))),
            ("<", Version("%d.%d.0" % (major, minor + 1))),
        ]
    ver = Version("%d.%d.%d" % (major, minor, patch))
    if "-" in rest.split("+", 1)[0]:
        pre = rest.split("+", 1)[0].split("-", 1)[1]
        ver.prerelease = tuple(pre.split("."))
    return [(op, ver)]


def _cmp_op(version, op, bound):
    if op == "*":
        return True
    if op == "=":
        return version == bound
    if op == ">=":
        return version >= bound
    if op == ">":
        return version > bound
    if op == "<=":
        return version <= bound
    if op == "<":
        return version < bound
    raise ValueError("unknown op %s" % op)


def _clause_allows_prerelease(comparators):
    for op, bound in comparators:
        if bound is not None and bound.prerelease:
            return True
    return False


def satisfies(version_text, spec):
    try:
        version = Version(version_text)
    except (TypeError, ValueError):
        return False
    spec = (spec or "*").strip()
    if spec in ("*", "", "x", "X"):
        return version.prerelease is None
    for clause in spec.split("||"):
        try:
            tokens = _split_comparators(clause)
            comparators = []
            for token in tokens:
                comparators.extend(_token_to_bounds(token))
        except (TypeError, ValueError):
            continue
        allow_pre = _clause_allows_prerelease(comparators)
        if version.prerelease and not allow_pre:
            continue
        if all(_cmp_op(version, op, bound) for op, bound in comparators):
            return True
    return False


def max_satisfying(versions, spec):
    matching = []
    for item in versions:
        if satisfies(item, spec):
            try:
                matching.append((Version(item), item))
            except (TypeError, ValueError):
                continue
    if not matching:
        return None
    matching.sort(key=lambda pair: pair[0])
    return matching[-1][1]
