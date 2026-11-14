"""A small, safe evaluator for rule conditions.

A condition such as
    brick_volume_qoq_pct <= -8 and days_since_rep_visit >= 60 and tier in ['A','B']
is parsed with Python's `ast` module into a tree, every node is checked against a whitelist (no function
calls except the four theme functions, no attribute access, no arithmetic beyond a minus sign), and the
tree is then evaluated over a whole DataFrame at once, like a SQL WHERE clause over a table.

Missing values behave as in SQL: a comparison with a blank is not true, so the rule does not fire.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field

import pandas as pd

ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.Compare,
                 ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Name, ast.Constant,
                 ast.List, ast.Tuple, ast.Call, ast.Load)
THEME_FUNCTIONS = {"theme_received", "theme_received_days_ago", "theme_ignored_count", "asset_variant_count"}
OPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
       ast.Gt: operator.gt, ast.GtE: operator.ge}


class ConditionError(ValueError):
    pass


@dataclass
class Context:
    """What the theme functions look up.
    themes: one row per (hcp_id, theme) with days_ago (since last received) and ignored_count.
    variants: one row per (market, brand, content_theme, channel) with n approved asset variants."""
    themes: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(
        columns=["hcp_id", "theme", "days_ago", "ignored_count"]))
    variants: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(
        columns=["market", "brand", "content_theme", "channel", "n"]))

    def __post_init__(self):
        self._t = self.themes.set_index(["hcp_id", "theme"])
        self._v = self.variants.set_index(["market", "brand", "content_theme", "channel"])["n"]

    def _lookup(self, df, theme, col):
        theme = theme if isinstance(theme, pd.Series) else pd.Series(theme, index=df.index)
        key = pd.MultiIndex.from_arrays([df["hcp_id"], theme])
        return pd.Series(self._t[col].reindex(key).to_numpy(), index=df.index)

    def theme_received(self, df, theme):
        return self._lookup(df, theme, "days_ago").notna()

    def theme_received_days_ago(self, df, theme):
        return self._lookup(df, theme, "days_ago")

    def theme_ignored_count(self, df, theme):
        return self._lookup(df, theme, "ignored_count").fillna(0)

    def asset_variant_count(self, df, theme, channel):
        def s(x):
            return x if isinstance(x, pd.Series) else pd.Series(x, index=df.index)
        key = pd.MultiIndex.from_arrays([df["market"], df["brand"], s(theme), s(channel)])
        return pd.Series(self._v.reindex(key).fillna(0).to_numpy(), index=df.index)


class Condition:
    def __init__(self, text: str):
        self.text = text
        try:
            self.tree = ast.parse(text.strip(), mode="eval")
        except SyntaxError as e:
            raise ConditionError(f"cannot read condition: {e.msg}") from None
        for node in ast.walk(self.tree):
            if not isinstance(node, ALLOWED_NODES):
                raise ConditionError(f"'{type(node).__name__}' is not allowed in a condition")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in THEME_FUNCTIONS:
                    raise ConditionError("only theme functions may be called: " + ", ".join(sorted(THEME_FUNCTIONS)))
                if node.keywords or not all(isinstance(a, (ast.Constant, ast.Name)) for a in node.args):
                    raise ConditionError(f"{node.func.id}() takes plain values or column names")

    # ------------------------------------------------------------------ introspection (for the linter)
    def columns(self) -> set[str]:
        funcs = {id(n.func) for n in ast.walk(self.tree) if isinstance(n, ast.Call)}
        return {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and id(n) not in funcs}

    def functions(self) -> set[str]:
        return {n.func.id for n in ast.walk(self.tree) if isinstance(n, ast.Call)}

    def text_comparisons(self) -> list[tuple[str, list]]:
        """(column, [text values]) for every `column == 'x'` or `column in ['x','y']`."""
        out = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name):
                for comp in n.comparators:
                    vals = [comp.value] if isinstance(comp, ast.Constant) else \
                        [e.value for e in getattr(comp, "elts", []) if isinstance(e, ast.Constant)]
                    vals = [v for v in vals if isinstance(v, str)]
                    if vals:
                        out.append((n.left.id, vals))
        return out

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, df: pd.DataFrame, ctx: Context | None = None) -> pd.Series:
        """True for every row where the condition holds."""
        ctx = ctx or Context()
        out = self._eval(self.tree.body, df, ctx)
        if not isinstance(out, pd.Series):
            out = pd.Series(bool(out), index=df.index)
        return out.astype("boolean").fillna(False).astype(bool)

    def _eval(self, node, df, ctx):
        if isinstance(node, ast.BoolOp):
            parts = [self._as_bool(self._eval(v, df, ctx), df) for v in node.values]
            res = parts[0]
            for p in parts[1:]:
                res = (res & p) if isinstance(node.op, ast.And) else (res | p)
            return res
        if isinstance(node, ast.UnaryOp):
            v = self._eval(node.operand, df, ctx)
            return ~self._as_bool(v, df) if isinstance(node.op, ast.Not) else -v
        if isinstance(node, ast.Compare):
            res, left = None, self._eval(node.left, df, ctx)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval(comp, df, ctx)
                step = self._compare(op, left, right, df)
                res = step if res is None else (res & step)
                left = right
            return res
        if isinstance(node, ast.Name):
            if node.id not in df.columns:
                raise ConditionError(f"no column '{node.id}' in the feature table")
            return df[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._eval(e, df, ctx) for e in node.elts]
        if isinstance(node, ast.Call):
            args = [self._eval(a, df, ctx) for a in node.args]
            return getattr(ctx, node.func.id)(df, *args)
        raise ConditionError(f"cannot evaluate {type(node).__name__}")

    @staticmethod
    def _as_bool(v, df):
        if not isinstance(v, pd.Series):
            return pd.Series(bool(v), index=df.index)
        return v.astype("boolean").fillna(False).astype(bool)

    @staticmethod
    def _compare(op, left, right, df):
        if isinstance(op, (ast.In, ast.NotIn)):
            if not isinstance(right, list):
                raise ConditionError("'in' needs a list, for example tier in ['A','B']")
            left = left if isinstance(left, pd.Series) else pd.Series(left, index=df.index)
            hit = left.isin(right)
            res = hit if isinstance(op, ast.In) else ~hit
            return res & left.notna()
        if isinstance(left, pd.Series) and isinstance(right, pd.Series) and \
                (left.dtype == object or right.dtype == object or str(left.dtype) == "string"):
            res = pd.Series(OPS[type(op)](left.astype(object).to_numpy(), right.astype(object).to_numpy()),
                            index=df.index)
        else:
            res = OPS[type(op)](left, right)
        if not isinstance(res, pd.Series):
            return pd.Series(bool(res), index=df.index)
        known = pd.Series(True, index=df.index)
        for side in (left, right):
            if isinstance(side, pd.Series):
                known &= side.notna()
        return res.astype("boolean").fillna(False).astype(bool) & known
