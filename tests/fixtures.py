"""Build a firing and a silent fixture row for any rule condition.

A condition is a list of atoms joined by `and`, for example
    brick_volume_qoq_pct <= -8 and days_since_rep_visit >= 60 and tier in ['A','B']
For the firing row we pick, atom by atom, a value that makes the atom true (-8, 60, 'A'). For the silent row
we make the first atom false and keep the rest true, so the row fails for exactly one reason.
Theme functions are satisfied by adding rows to the theme history or the asset variant list.
"""
from __future__ import annotations

import ast

import pandas as pd

from nba.rules.expr import Context

OTHER = "zz_other"
BASE = {"hcp_id": "FIX-H00001", "market": "UK", "brand": "Movicol"}


class Unsupported(Exception):
    pass


def _const(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_const(node.operand)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_const(e) for e in node.elts]
    raise Unsupported(ast.dump(node))


def _value(op, c, truth: bool):
    """A value v with (v op c) == truth."""
    if isinstance(op, (ast.In, ast.NotIn)):
        hit = truth if isinstance(op, ast.In) else not truth
        return c[0] if hit else OTHER
    if isinstance(c, bool):
        same = truth if isinstance(op, ast.Eq) else not truth
        return c if same else (not c)
    if isinstance(c, str):
        same = truth if isinstance(op, ast.Eq) else not truth
        return c if same else OTHER
    if isinstance(op, ast.Eq):
        return c if truth else c + 1
    if isinstance(op, ast.NotEq):
        return c + 1 if truth else c
    if isinstance(op, ast.Lt):
        return c - 1 if truth else c
    if isinstance(op, ast.LtE):
        return c if truth else c + 1
    if isinstance(op, ast.Gt):
        return c + 1 if truth else c
    if isinstance(op, ast.GtE):
        return c if truth else c - 1
    raise Unsupported(type(op).__name__)


def _atoms(tree):
    body = tree.body
    atoms = body.values if isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And) else [body]
    for a in atoms:
        if not isinstance(a, ast.Compare) or len(a.ops) != 1:
            raise Unsupported("only 'and' of single comparisons is generated automatically")
    return atoms


def _arg(node, row, default):
    if isinstance(node, ast.Constant):
        return node.value
    row.setdefault(node.id, default)
    return row[node.id]


def build(tree, truths: list[bool]):
    """Return (row dict, Context) where atom i evaluates to truths[i]."""
    row, themes, variants = dict(BASE), [], []
    for atom, truth in zip(_atoms(tree), truths):
        left, op, right = atom.left, atom.ops[0], atom.comparators[0]
        if isinstance(left, ast.Name) and isinstance(right, ast.Name):
            numeric = isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
            row.setdefault(right.id, 5 if numeric else "X")
            row[left.id] = _value(op, row[right.id], truth)
        elif isinstance(left, ast.Name):
            row[left.id] = _value(op, _const(right), truth)
        elif isinstance(left, ast.Call):
            fn, c = left.func.id, _const(right)
            v = _value(op, c, truth)
            theme = _arg(left.args[0], row, "efficacy")
            if fn == "theme_received":
                if v:
                    themes.append(dict(hcp_id=BASE["hcp_id"], theme=theme, days_ago=10, ignored_count=0))
            elif fn == "theme_received_days_ago":
                themes.append(dict(hcp_id=BASE["hcp_id"], theme=theme, days_ago=v, ignored_count=0))
            elif fn == "theme_ignored_count":
                themes.append(dict(hcp_id=BASE["hcp_id"], theme=theme, days_ago=10, ignored_count=v))
            elif fn == "asset_variant_count":
                channel = _arg(left.args[1], row, "rep_email")
                variants.append(dict(market=row["market"], brand=row["brand"], content_theme=theme,
                                     channel=channel, n=v))
            else:
                raise Unsupported(fn)
        else:
            raise Unsupported(ast.dump(atom))
    ctx = Context(themes=pd.DataFrame(themes, columns=["hcp_id", "theme", "days_ago", "ignored_count"]),
                  variants=pd.DataFrame(variants, columns=["market", "brand", "content_theme", "channel", "n"]))
    return row, ctx


def firing_and_silent(tree):
    n = len(_atoms(tree))
    fire = build(tree, [True] * n)
    silent = build(tree, [False] + [True] * (n - 1))
    return fire, silent
