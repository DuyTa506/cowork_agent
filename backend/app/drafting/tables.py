"""Tables of a draft: the spec the assistant and the user write, the figures worked out from it, and the layout the renderer and
the canvas draw from it.

A table is described, never drawn, by the model: columns (a column may have one level of sub-columns, "Số lượng" over "Hiện có"
and "Đề xuất"), then rows of four types:

* ``row``     — an ordinary line, one cell per leaf column
* ``group``   — a heading line inside the table ("I", "Trang thiết bị phần cứng"), bold, its other cells left empty
* ``section`` — one text across the whole width ("Bổ sung (số lượng căn cứ theo ...)"), centred and bold
* ``total``   — the "Cộng" line, bold

Every column and row has an id ("c3", "r12") that stays with it when others are inserted or deleted, so an edit can name the
cell it changes and a proposal can be compared with the table cell by cell. Ids are never reused within a table (``seq`` keeps
the last one handed out).

Figures are worked out by code, never by the model: a leaf column may have a ``formula`` (``c4 * c5``, ``c5 / sum(c5) * 100``)
computed on each ordinary row, and a ``total`` or ``group`` row may ``sum`` columns over its rows. A figure nobody has given is
"…"; anything computed from it is "…" too, so a total never leaves out a missing figure.

Thông tư 68 does not size the text of a table; the units' own appendices use 13 pt with bold column headings, which is what the
renderer prints. A table too wide for a portrait page turns its appendix landscape (TT68 Phụ lục I, mục I.2: a document with tables
may be laid out across the width of the A4 sheet, with the same margins).
"""
from __future__ import annotations

import copy
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Callable

from app.core.errors import ValidationFailed

from . import metrics
from .markup import clean

ROW_TYPES = ("row", "group", "section", "total")
ALIGNS = ("left", "center", "right")
SCOPES = ("all", "group")
MAX_COLUMNS = 16
MAX_ROWS = 500
MAX_CELL = 1000
MAX_FORMULA = 200
MAX_OPS = 200
TABLE_PT = 13
PORTRAIT_CM, LANDSCAPE_CM = 16.0, 24.7  # text width of an A4 page with the TT68 margins (30 mm left, 20 mm right)
CELL_PAD_CM = 0.4  # left and right cell margins plus a little air
GAP = "…"
_NUMBER = re.compile(r"^[\d.,%/()+\-–\s…]*$")
_ORDINAL_LABELS = {"tt", "stt", "số tt", "số thứ tự"}
_IDS = {"c": re.compile(r"^c(\d{1,6})$"), "r": re.compile(r"^r(\d{1,6})$")}
_BOUNDARIES = ("group", "section")


def _text(value: Any) -> str:
    """A label or cell as plain text.

    Raises:
        ValidationFailed: The text is longer than `MAX_CELL`.
    """
    text = clean(str(value if value is not None else "")).strip()
    if len(text) > MAX_CELL:
        raise ValidationFailed(f"Ô bảng quá dài (tối đa {MAX_CELL} ký tự).")
    return text


# ----- figures written the Vietnamese way -----
_GROUPED = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$")  # 1.234.567 or 1.234,5
_PLAIN = re.compile(r"^\d+(?:,\d+)?$")  # 1234 or 12,5
_DOT_DECIMAL = re.compile(r"^\d+\.\d+$")  # 1.5: not a thousands group, so a decimal point
_DASHES = {"-", "–", "—", "−"}
_FIGURE = re.compile(r"(?<![\w.,/])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![\w/]|[.,]\d)")


def is_gap(text: str) -> bool:
    """Whether a cell still waits for its figure: empty, or holding "…"."""
    text = (text or "").strip()
    return not text or GAP in text or "..." in text


def parse_number(text: str) -> Decimal | None:
    """Reads a figure written the Vietnamese way.

    The dot groups thousands and the comma marks decimals ("1.200" is one thousand two hundred, "12,5" twelve and a half); a dot
    not followed by groups of three digits is read as a decimal point ("1.5"). A trailing "%" is ignored, and a lone dash means
    none (0), as in the statistical tables.

    Args:
        text: The cell.

    Returns:
        The value, or None when the cell is not a figure (text, a gap, "1,234.5").
    """
    text = (text or "").strip().replace("\u00a0", "").replace(" ", "")
    if text in _DASHES:
        return Decimal(0)
    sign = 1
    if text[:1] in ("-", "−", "–"):
        sign, text = -1, text[1:]
    elif text[:1] == "+":
        text = text[1:]
    text = text.removesuffix("%")
    if _GROUPED.match(text):
        digits = text.replace(".", "").replace(",", ".")
    elif _PLAIN.match(text):
        digits = text.replace(",", ".")
    elif _DOT_DECIMAL.match(text):
        digits = text
    else:
        return None
    return sign * Decimal(digits)


def format_number(value: Decimal) -> str:
    """Writes a figure the Vietnamese way: thousands grouped by dots, at most two decimals after a comma ("1.234,57")."""
    with localcontext() as context:
        context.prec = 60
        value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{abs(value):f}".partition(".")
    fraction = fraction.rstrip("0")
    text = f"{int(whole):,}".replace(",", ".") + (f",{fraction}" if fraction else "")
    return f"-{text}" if value < 0 and text != "0" else text


def figures_in(text: str) -> set[Decimal]:
    """The figures written in a passage of text (dates such as "10/6/2026" excluded)."""
    out = set()
    for match in _FIGURE.finditer(text or ""):
        value = parse_number(match.group(1))
        if value is not None:
            out.add(value)
    return out


# ----- formulas -----
_OPERATORS = str.maketrans({"×": "*", "÷": "/", ":": "/", "−": "-", "–": "-"})
_TOKEN = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?)|([A-Za-z]\w*)|(\S))")


class _Unknown:
    """The value of a gap ("…") while computing: whatever depends on it is unknown as well."""


_UNKNOWN = _Unknown()


class _NotNumber(Exception):
    def __init__(self, column: str, text: str):
        super().__init__(column)
        self.column, self.text = column, text


class _DivisionByZero(Exception):
    pass


def _tokens(formula: str, label: str) -> list[tuple[str, str]]:
    """Splits a formula into numbers, names and operators.

    Raises:
        ValidationFailed: A character a formula may not hold.
    """
    text, out, pos = formula.translate(_OPERATORS).strip(), [], 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        number, name, symbol = match.groups()
        if number:
            out.append(("num", number))
        elif name:
            out.append(("name", name.lower()))
        elif symbol in "+-*/()":
            out.append(("op", symbol))
        else:
            raise _formula_error(formula, label, f"ký tự '{symbol}' không dùng được")
        pos = match.end()
    return out


def _formula_error(formula: str, label: str, why: str) -> ValidationFailed:
    return ValidationFailed(f"Công thức '{formula}' của cột '{label}' không hợp lệ ({why}): chỉ dùng số, mã cột (c3), sum(c3), "
                            "các phép + - × ÷ và ngoặc.")


class _Parser:
    """Recursive descent over ``expr := term (('+'|'-') term)*``, ``term := factor (('*'|'/') factor)*``,
    ``factor := ('-'|'+') factor | number | column | 'sum' '(' column ')' | '(' expr ')'``."""

    def __init__(self, formula: str, label: str):
        self.formula, self.label = formula, label
        self.tokens, self.at = _tokens(formula, label), 0

    def parse(self) -> tuple:
        node = self._expr()
        if self.at != len(self.tokens):
            raise self._error(f"thừa '{self.tokens[self.at][1]}'")
        return node

    def _error(self, why: str) -> ValidationFailed:
        return _formula_error(self.formula, self.label, why)

    def _peek(self) -> tuple[str, str]:
        return self.tokens[self.at] if self.at < len(self.tokens) else ("end", "")

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        self.at += 1
        return token

    def _expect(self, token: tuple[str, str]) -> None:
        if self._take() != token:
            raise self._error(f"thiếu '{token[1]}'")

    def _expr(self) -> tuple:
        node = self._term()
        while self._peek() in (("op", "+"), ("op", "-")):
            node = (self._take()[1], node, self._term())
        return node

    def _term(self) -> tuple:
        node = self._factor()
        while self._peek() in (("op", "*"), ("op", "/")):
            node = (self._take()[1], node, self._factor())
        return node

    def _factor(self) -> tuple:
        kind, value = self._take()
        if (kind, value) == ("op", "-"):
            return ("neg", self._factor())
        if (kind, value) == ("op", "+"):
            return self._factor()
        if kind == "num":
            return ("num", Decimal(value.replace(",", ".")))
        if (kind, value) == ("op", "("):
            node = self._expr()
            self._expect(("op", ")"))
            return node
        if kind == "name" and value == "sum":
            self._expect(("op", "("))
            kind, column = self._take()
            if kind != "name" or not _IDS["c"].match(column):
                raise self._error("sum() nhận một mã cột")
            self._expect(("op", ")"))
            return ("sum", column)
        if kind == "name" and _IDS["c"].match(value):
            return ("col", value)
        raise self._error(f"không hiểu '{value}'" if value else "thiếu số hoặc mã cột ở cuối")


def _parse(formula: str, label: str) -> tuple:
    """The syntax tree of a formula (see `_Parser`)."""
    return _Parser(formula, label).parse()


def _refs(node: tuple) -> set[str]:
    """The column ids a formula reads, as a cell or through sum()."""
    if node[0] in ("col", "sum"):
        return {node[1]}
    if node[0] == "num":
        return set()
    return set().union(*(_refs(child) for child in node[1:]))


def _evaluate(node: tuple, cell: Callable[[str], Any], total: Callable[[str], Any]) -> Any:
    """Computes a formula.

    Args:
        node: Its syntax tree.
        cell: The value of a column on the row being computed.
        total: The sum of a column over the ordinary rows of the table.

    Returns:
        A Decimal, or `_UNKNOWN` when a figure it needs is a gap.

    Raises:
        _NotNumber: A cell it reads is text.
        _DivisionByZero: A division by zero.
    """
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "col":
        return cell(node[1])
    if kind == "sum":
        return total(node[1])
    if kind == "neg":
        value = _evaluate(node[1], cell, total)
        return value if value is _UNKNOWN else -value
    left, right = _evaluate(node[1], cell, total), _evaluate(node[2], cell, total)
    if left is _UNKNOWN or right is _UNKNOWN:
        return _UNKNOWN
    if kind == "+":
        return left + right
    if kind == "-":
        return left - right
    if kind == "*":
        return left * right
    if right == 0:
        raise _DivisionByZero()
    return left / right


def _order(deps: dict[str, set[str]], labels: dict[str, str]) -> list[str]:
    """The formula columns in an order where each comes after the columns it reads.

    Raises:
        ValidationFailed: Formulas that read each other in a circle.
    """
    order: list[str] = []
    state: dict[str, str] = {}

    def visit(column: str, path: list[str]) -> None:
        if state.get(column) == "done":
            return
        if state.get(column) == "busy":
            if path == [column]:
                raise ValidationFailed(f"Công thức của cột '{labels.get(column, column)}' dùng chính cột đó.")
            circle = [*path[path.index(column):], column]
            raise ValidationFailed("Công thức các cột dùng lẫn nhau thành vòng: " + " > ".join(labels.get(c, c) for c in circle) + ".")
        state[column] = "busy"
        for ref in sorted(deps.get(column, ())):
            if ref in deps:
                visit(ref, [*path, column])
        state[column] = "done"
        order.append(column)

    for column in deps:
        visit(column, [])
    return order


# ----- the spec -----
def _column(raw: Any, depth: int) -> dict[str, Any]:
    """One column checked and tidied.

    Args:
        raw: ``{"id"?, "label", "align"?, "formula"?, "children"?}``, or just the label.
        depth: 0 for a top-level column, 1 for a sub-column.

    Returns:
        ``{"id", "label", "align"?, "formula"?, "children"?}`` with plain-text labels; the id may still be empty or invalid
        (`_assign_ids` settles it).

    Raises:
        ValidationFailed: No label, an unknown alignment, sub-columns under a sub-column, a formula on a column with sub-columns
            or longer than `MAX_FORMULA`.
    """
    if isinstance(raw, str):
        raw = {"label": raw}
    if not isinstance(raw, dict):
        raise ValidationFailed("Mỗi cột của bảng phải có 'label'.")
    label = _text(raw.get("label", ""))
    if not label:
        raise ValidationFailed("Cột của bảng thiếu tên ('label').")
    align = raw.get("align") or ""
    if align and align not in ALIGNS:
        raise ValidationFailed("align của cột phải là left, center hoặc right.")
    out: dict[str, Any] = {"id": str(raw.get("id") or "").strip(), "label": label}
    if align:
        out["align"] = align
    formula = str(raw.get("formula") or "").strip()
    children = raw.get("children") or []
    if children:
        if depth > 0:
            raise ValidationFailed("Tiêu đề cột chỉ được tối đa hai tầng.")
        if formula:
            raise ValidationFailed(f"Cột '{label}' có cột con nên không đặt công thức; đặt ở từng cột con.")
        out["children"] = [_column(child, 1) for child in children]
    elif formula:
        if len(formula) > MAX_FORMULA:
            raise ValidationFailed(f"Công thức của cột '{label}' quá dài (tối đa {MAX_FORMULA} ký tự).")
        out["formula"] = formula
    return out


def _row(raw: Any, width: int) -> dict[str, Any]:
    """One row checked and tidied.

    Args:
        raw: ``{"id"?, "type"?, "cells", "sum"?, "scope"?}``, or a bare list of cells.
        width: Number of leaf columns.

    Returns:
        ``{"id", "type", "cells", "sum"?, "scope"?}``, as wide as the leaf columns (a ``section`` row keeps one cell).

    Raises:
        ValidationFailed: An unknown row type or scope, more cells than columns, or ``sum`` on a row that is not a total or group.
    """
    if isinstance(raw, list):
        raw = {"cells": raw}
    if not isinstance(raw, dict):
        raise ValidationFailed("Mỗi dòng của bảng phải có 'cells'.")
    kind = raw.get("type") or "row"
    if kind not in ROW_TYPES:
        raise ValidationFailed("Loại dòng của bảng phải là row, group, section hoặc total.")
    cells = [_text(c) for c in (raw.get("cells") or [])]
    if len(cells) > width:
        raise ValidationFailed(f"Dòng có {len(cells)} ô trong khi bảng có {width} cột.")
    if kind == "section":
        cells = [" ".join(c for c in cells if c)]
    else:
        cells += [""] * (width - len(cells))
    out: dict[str, Any] = {"id": str(raw.get("id") or "").strip(), "type": kind, "cells": cells}
    sums = list(dict.fromkeys(str(c).strip() for c in raw.get("sum") or [] if str(c).strip()))
    if sums:
        if kind not in ("group", "total"):
            raise ValidationFailed("Chỉ dòng 'total' (Cộng) hoặc dòng 'group' mới tự cộng cột ('sum').")
        out["sum"] = sums
        if kind == "total":
            scope = raw.get("scope") or "all"
            if scope not in SCOPES:
                raise ValidationFailed("scope của dòng cộng phải là all (cả bảng) hoặc group (nhóm chứa dòng đó).")
            out["scope"] = scope
    return out


def _nodes(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every column, top-level and sub-column, in order."""
    return [node for column in columns for node in (column, *(column.get("children") or []))]


def _assign_ids(columns: list[dict[str, Any]], rows: list[dict[str, Any]], seq: Any) -> dict[str, int]:
    """Gives every column and row an id, keeping the valid ones it already has.

    Args:
        columns: Top-level columns (changed in place).
        rows: Rows (changed in place).
        seq: The spec's ``seq`` (``{"c": last column number, "r": last row number}``), if any.

    Returns:
        The new ``seq``. A missing, malformed or repeated id is replaced by the next number, past both ``seq`` and every id in use,
        so a deleted id is not handed out again.
    """
    last: dict[str, int] = {}
    for prefix, items in (("c", _nodes(columns)), ("r", rows)):
        given = seq.get(prefix) if isinstance(seq, dict) else None
        top = given if isinstance(given, int) and not isinstance(given, bool) and given >= 0 else 0
        for item in items:
            match = _IDS[prefix].match(str(item.get("id") or ""))
            if match:
                top = max(top, int(match.group(1)))
        seen: set[str] = set()
        for item in items:
            ident = str(item.get("id") or "")
            if not _IDS[prefix].match(ident) or ident in seen:
                top += 1
                ident = f"{prefix}{top}"
            seen.add(ident)
            item["id"] = ident
        last[prefix] = top
    return last


def _check_calculations(spec: dict[str, Any]) -> None:
    """Checks the formulas and sums of a spec whose ids are settled.

    Raises:
        ValidationFailed: A formula that does not parse, reads a column the table does not have or reads itself (directly or
            in a circle); a row summing a column the table does not have.
    """
    leaves_ = _leaves(spec["columns"])
    known = {leaf["id"] for leaf in leaves_}
    labels = {leaf["id"]: leaf["label"] for leaf in leaves_}
    deps = {}
    for leaf in leaves_:
        if leaf.get("formula"):
            refs = _refs(_parse(leaf["formula"], leaf["label"]))
            unknown = sorted(refs - known)
            if unknown:
                raise ValidationFailed(f"Công thức của cột '{leaf['label']}' dùng cột không có: {', '.join(unknown)}.")
            deps[leaf["id"]] = refs
    _order(deps, labels)
    for row in spec["rows"]:
        unknown = [c for c in row.get("sum") or [] if c not in known]
        if unknown:
            raise ValidationFailed(f"Dòng {row['id']} cộng cột không có: {', '.join(unknown)}.")


def normalize(raw: Any) -> dict[str, Any]:
    """Checks and tidies a table spec, and works out its formulas and sums.

    Args:
        raw: ``{"columns": [...], "rows": [...], "seq"?, "landscape"?: bool}`` as the assistant or the canvas sent it. A row may
            be a bare list of cells; ids may be missing.

    Returns:
        ``{"columns", "rows", "seq", "landscape"?}``: labels and cells as plain text, every row as wide as the leaf columns (a
        ``section`` row keeps one cell), every column and row with an id, computed cells filled, and ``landscape`` only when it
        was given.

    Raises:
        ValidationFailed: No column, more than `MAX_COLUMNS` leaf columns or `MAX_ROWS` rows, a third heading level, an unknown
            row type, a row with more cells than columns, or a formula or sum that cannot be worked out (see
            `_check_calculations`).
    """
    if not isinstance(raw, dict):
        raise ValidationFailed("Bảng phải có 'columns' và 'rows'.")
    columns = [_column(c, 0) for c in raw.get("columns") or []]
    if not columns:
        raise ValidationFailed("Bảng phải có ít nhất một cột.")
    width = len(_leaves(columns))
    if width > MAX_COLUMNS:
        raise ValidationFailed(f"Bảng tối đa {MAX_COLUMNS} cột.")
    rows_in = raw.get("rows") or []
    if len(rows_in) > MAX_ROWS:
        raise ValidationFailed(f"Bảng tối đa {MAX_ROWS} dòng.")
    rows = [_row(row, width) for row in rows_in]
    out: dict[str, Any] = {"columns": columns, "rows": rows, "seq": _assign_ids(columns, rows, raw.get("seq"))}
    if raw.get("landscape") is not None:
        out["landscape"] = bool(raw["landscape"])
    _check_calculations(out)
    compute(out)
    return out


def ensure_ids(spec: dict[str, Any]) -> dict[str, Any]:
    """A stored spec with ids on its columns and rows.

    Tables saved before they had ids get them by position, the same each time the draft is read, until the draft is next written
    and they are stored.

    Args:
        spec: A stored spec.

    Returns:
        `spec` itself when every column and row has an id, else a copy with ids.
    """
    columns, rows = spec.get("columns") or [], spec.get("rows") or []
    if isinstance(spec.get("seq"), dict) and all(item.get("id") for item in (*_nodes(columns), *rows)):
        return spec
    out = copy.deepcopy(spec)
    out["seq"] = _assign_ids(out.get("columns") or [], out.get("rows") or [], out.get("seq"))
    return out


def _leaves(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The columns that hold cells: each sub-column, or the column itself when it has none."""
    return [leaf for column in columns for leaf in (column.get("children") or [column])]


def leaves(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The columns of a normalised spec that hold cells, left to right.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        The leaf columns (``{"id", "label", "align"?, "formula"?}``).
    """
    return _leaves(spec["columns"])


# ----- computed cells -----
def computed(row: dict[str, Any], leaf: dict[str, Any]) -> bool:
    """Whether a cell is worked out by the table rather than typed.

    Args:
        row: A row of the spec.
        leaf: A leaf column of the spec.

    Returns:
        True for a formula column on an ordinary row, and on a row that sums columns, for the summed columns and the formula
        columns (worked out from the sums, so a percentage of the totals is not a sum of percentages).
    """
    if row["type"] == "row":
        return bool(leaf.get("formula"))
    if row["type"] in ("group", "total") and row.get("sum"):
        return leaf["id"] in row["sum"] or bool(leaf.get("formula"))
    return False


def _scope(rows: list[dict[str, Any]], target: dict[str, Any]) -> list[dict[str, Any]]:
    """The ordinary rows a summing row adds up.

    A ``total`` row with scope ``all`` adds every ordinary row of the table, wherever it stands (some tables put "Tổng số" first).
    A ``group`` row adds the rows after it up to the next group or section row; a ``total`` row with scope ``group`` adds the rows
    of the group it stands in.
    """
    if target["type"] == "total" and target.get("scope", "all") == "all":
        return [row for row in rows if row["type"] == "row"]
    at = next(i for i, row in enumerate(rows) if row is target)
    low = at if target["type"] == "group" else max((i for i in range(at) if rows[i]["type"] in _BOUNDARIES), default=-1)
    high = min((i for i in range(at + 1, len(rows)) if rows[i]["type"] in _BOUNDARIES), default=len(rows))
    return [row for row in rows[low + 1:high] if row["type"] == "row"]


def compute(spec: dict[str, Any]) -> list[str]:
    """Fills the cells worked out by formulas and sums.

    Formula columns are computed on each ordinary row, in the order they depend on each other; then each summing row adds its
    columns over its rows and computes the formula columns it does not sum from its own cells. A gap in what a cell needs makes
    the cell a gap ("…"); so do text where a figure is needed and a division by zero, which are reported.

    Args:
        spec: A spec with settled ids and checked formulas (changed in place).

    Returns:
        The problems, one sentence each ("Dòng r3, cột 'Tỷ lệ': chia cho 0.").
    """
    leaves_ = _leaves(spec["columns"])
    index = {leaf["id"]: i for i, leaf in enumerate(leaves_)}
    labels = {leaf["id"]: leaf["label"] for leaf in leaves_}
    formulas = {leaf["id"]: _parse(leaf["formula"], leaf["label"]) for leaf in leaves_ if leaf.get("formula")}
    order = _order({column: _refs(tree) for column, tree in formulas.items()}, labels)
    rows = spec["rows"]
    data = [row for row in rows if row["type"] == "row"]
    problems: list[str] = []

    def value(row: dict[str, Any], column: str) -> Any:
        text = row["cells"][index[column]]
        if is_gap(text):
            return _UNKNOWN
        number = parse_number(text)
        if number is None:
            raise _NotNumber(column, text)
        return number

    def total(over: list[dict[str, Any]], column: str) -> Any:
        out = Decimal(0)
        for row in over:
            number = value(row, column)
            if number is _UNKNOWN:
                return _UNKNOWN
            out += number
        return out

    def by_formula(row: dict[str, Any], column: str) -> Any:
        return _evaluate(formulas[column], lambda ref: value(row, ref), lambda ref: total(data, ref))

    def fill(row: dict[str, Any], column: str, work: Callable[[], Any]) -> None:
        try:
            result = work()
        except _NotNumber as exc:
            problems.append(f"Dòng {row['id']}, cột '{labels[column]}': ô cột '{labels[exc.column]}' ('{exc.text}') không phải số.")
            result = _UNKNOWN
        except _DivisionByZero:
            problems.append(f"Dòng {row['id']}, cột '{labels[column]}': chia cho 0.")
            result = _UNKNOWN
        row["cells"][index[column]] = GAP if result is _UNKNOWN else format_number(result)

    with localcontext() as context:
        context.prec = 40
        for column in order:
            for row in data:
                fill(row, column, lambda: by_formula(row, column))  # noqa: B023  (called at once)
        for row in rows:
            sums = row.get("sum") or []
            if not sums:
                continue
            over = _scope(rows, row)
            for column in sums:
                fill(row, column, lambda: total(over, column))  # noqa: B023
            for column in order:
                if column not in sums:
                    fill(row, column, lambda: by_formula(row, column))  # noqa: B023
    return problems


def problems(spec: dict[str, Any]) -> list[str]:
    """What the table could not work out (text where a figure is needed, a division by zero); see `compute`."""
    return compute(copy.deepcopy(spec))


# ----- edits by id -----
def _need(op: dict[str, Any], key: str) -> str:
    """A required argument of an operation."""
    value = str(op.get(key) or "").strip()
    if not value:
        raise ValidationFailed(f"thiếu '{key}'.")
    return value


def _find_row(work: dict[str, Any], row_id: str) -> tuple[int, dict[str, Any]]:
    for at, row in enumerate(work["rows"]):
        if row["id"] == row_id:
            return at, row
    raise ValidationFailed(f"không có dòng '{row_id}'.")


def _find_column(work: dict[str, Any], column_id: str) -> tuple[list[dict[str, Any]], int, dict[str, Any], dict[str, Any] | None]:
    """``(the list holding the column, its index there, the column, its group or None)``."""
    for at, column in enumerate(work["columns"]):
        if column["id"] == column_id:
            return work["columns"], at, column, None
        for sub_at, child in enumerate(column.get("children") or []):
            if child["id"] == column_id:
                return column["children"], sub_at, child, column
    raise ValidationFailed(f"không có cột '{column_id}'.")


def _leaf(work: dict[str, Any], column_id: str) -> tuple[int, dict[str, Any]]:
    """``(index among the leaf columns, the column)`` of a column that holds cells."""
    for at, leaf in enumerate(_leaves(work["columns"])):
        if leaf["id"] == column_id:
            return at, leaf
    _find_column(work, column_id)
    raise ValidationFailed(f"cột '{column_id}' có cột con; chọn một cột con.")


def _next_id(work: dict[str, Any], prefix: str) -> str:
    seq = work.setdefault("seq", {})
    seq[prefix] = seq.get(prefix, 0) + 1
    return f"{prefix}{seq[prefix]}"


def _place(items: list[dict[str, Any]], op: dict[str, Any], find: Callable[[str], int]) -> int:
    """Where an inserted row or column goes: after ``after``, before ``before``, or at the end."""
    if op.get("after"):
        return find(op["after"]) + 1
    if op.get("before"):
        return find(op["before"])
    return len(items)


def _op_set(work: dict[str, Any], op: dict[str, Any]) -> str:
    _, row = _find_row(work, _need(op, "row"))
    value = _text(op.get("value", ""))
    if row["type"] == "section":
        row["cells"] = [value]
        return ""
    at, leaf = _leaf(work, _need(op, "column"))
    if computed(row, leaf):
        raise ValidationFailed(f"ô {row['id']}/{leaf['id']} được tính tự động (công thức hoặc dòng cộng): sửa số liệu nguồn.")
    row["cells"][at] = value
    return ""


def _op_set_row(work: dict[str, Any], op: dict[str, Any]) -> str:
    _, row = _find_row(work, _need(op, "row"))
    if op.get("type"):
        if op["type"] not in ROW_TYPES:
            raise ValidationFailed("loại dòng phải là row, group, section hoặc total.")
        row["type"] = op["type"]
        if row["type"] not in ("group", "total"):
            row.pop("sum", None)
            row.pop("scope", None)
    if op.get("cells") is not None:
        row["cells"] = [_text(c) for c in op["cells"]]
    return ""


def _op_insert_row(work: dict[str, Any], op: dict[str, Any]) -> str:
    rows = work["rows"]
    if len(rows) >= MAX_ROWS:
        raise ValidationFailed(f"bảng tối đa {MAX_ROWS} dòng.")
    new: dict[str, Any] = {"id": _next_id(work, "r"), "type": op.get("type") or "row", "cells": list(op.get("cells") or [])}
    if op.get("columns"):
        new["sum"] = list(op["columns"])
        if op.get("scope"):
            new["scope"] = op["scope"]
    rows.insert(_place(rows, op, lambda ident: _find_row(work, ident)[0]), new)
    return f"Thêm dòng {new['id']}."


def _op_delete_row(work: dict[str, Any], op: dict[str, Any]) -> str:
    at, row = _find_row(work, _need(op, "row"))
    del work["rows"][at]
    return f"Xóa dòng {row['id']}."


def _op_insert_column(work: dict[str, Any], op: dict[str, Any]) -> str:
    label = _text(_need(op, "label"))
    if len(_leaves(work["columns"])) >= MAX_COLUMNS:
        raise ValidationFailed(f"bảng tối đa {MAX_COLUMNS} cột.")
    new: dict[str, Any] = {"id": _next_id(work, "c"), "label": label}
    if op.get("align"):
        new["align"] = op["align"]
    if op.get("formula"):
        new["formula"] = op["formula"]
    anchor, parent_id = op.get("after") or op.get("before") or "", op.get("parent") or ""
    if anchor:
        siblings, at, _, parent = _find_column(work, anchor)
        if parent_id and (parent is None or parent["id"] != parent_id):
            raise ValidationFailed(f"cột '{anchor}' không nằm dưới cột '{parent_id}'.")
        siblings.insert(at + 1 if op.get("after") else at, new)
    elif parent_id:
        _, _, parent, grand = _find_column(work, parent_id)
        if grand is not None or not parent.get("children"):
            raise ValidationFailed(f"cột '{parent_id}' không có cột con; chỉ thêm cột con vào cột nhóm.")
        parent["children"].append(new)
    else:
        work["columns"].append(new)
    values = op.get("values") or {}
    known = {row["id"] for row in work["rows"]}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValidationFailed(f"không có dòng {', '.join(unknown)}.")
    at = [leaf["id"] for leaf in _leaves(work["columns"])].index(new["id"])
    for row in work["rows"]:
        if row["type"] != "section":
            row["cells"].insert(at, _text(values.get(row["id"], "")))
    return f"Thêm cột {new['id']} ('{label}')."


def _op_delete_column(work: dict[str, Any], op: dict[str, Any]) -> str:
    column_id = _need(op, "column")
    siblings, at, node, parent = _find_column(work, column_id)
    gone = {leaf["id"] for leaf in node.get("children") or [node]}
    leaves_ = _leaves(work["columns"])
    if len(leaves_) == len(gone):
        raise ValidationFailed("bảng phải còn ít nhất một cột.")
    readers = [leaf["label"] for leaf in leaves_ if leaf["id"] not in gone and leaf.get("formula")
               and _refs(_parse(leaf["formula"], leaf["label"])) & gone]
    if readers:
        raise ValidationFailed(f"cột '{node['label']}' đang được dùng trong công thức của cột {', '.join(readers)}: sửa công thức trước.")
    positions = sorted((i for i, leaf in enumerate(leaves_) if leaf["id"] in gone), reverse=True)
    for row in work["rows"]:
        if row["type"] != "section":
            for position in positions:
                del row["cells"][position]
        if row.get("sum"):
            row["sum"] = [c for c in row["sum"] if c not in gone]
            if not row["sum"]:
                row.pop("sum")
                row.pop("scope", None)
    del siblings[at]
    if parent is not None and not parent["children"]:
        work["columns"].remove(parent)
    return f"Xóa cột {column_id} ('{node['label']}')."


def _op_rename_column(work: dict[str, Any], op: dict[str, Any]) -> str:
    _, _, node, _ = _find_column(work, _need(op, "column"))
    node["label"] = _text(_need(op, "label"))
    return ""


def _op_formula(work: dict[str, Any], op: dict[str, Any]) -> str:
    _, leaf = _leaf(work, _need(op, "column"))
    formula = str(op.get("formula") or "").strip()
    if formula:
        leaf["formula"] = formula
    else:
        leaf.pop("formula", None)
    return ""


def _op_total(work: dict[str, Any], op: dict[str, Any]) -> str:
    _, row = _find_row(work, _need(op, "row"))
    if row["type"] not in ("group", "total"):
        raise ValidationFailed(f"dòng {row['id']} không phải dòng cộng (total) hay dòng nhóm (group).")
    columns = list(op.get("columns") or [])
    for column in columns:
        _leaf(work, column)
    if columns:
        row["sum"] = columns
        if row["type"] == "total":
            row["scope"] = op.get("scope") or row.get("scope") or "all"
    else:
        row.pop("sum", None)
        row.pop("scope", None)
    return ""


_OPS: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "set": _op_set, "set_row": _op_set_row, "insert_row": _op_insert_row, "delete_row": _op_delete_row,
    "insert_column": _op_insert_column, "delete_column": _op_delete_column, "rename_column": _op_rename_column,
    "formula": _op_formula, "total": _op_total}
OPS = tuple(_OPS)


def apply(spec: dict[str, Any], ops: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """Applies edits that name rows and columns by id.

    Args:
        spec: A normalised spec (not changed).
        ops: The edits, in order. ``set`` {row, column, value}; ``set_row`` {row, cells?, type?}; ``insert_row`` {after? | before?,
            type?, cells?, columns?, scope?} (at the end without after/before; ``columns`` makes a total row sum them);
            ``delete_row`` {row}; ``insert_column`` {label, after? | before?, parent?, align?, formula?, values? {row id: text}};
            ``delete_column`` {column}; ``rename_column`` {column, label}; ``formula`` {column, formula} (empty removes it);
            ``total`` {row, columns, scope?} (empty columns stops the sums).

    Returns:
        ``(the new normalised spec, notes)``; the notes name the rows and columns created or removed ("Thêm dòng r12.").

    Raises:
        ValidationFailed: No edit, more than `MAX_OPS`, an unknown operation, row or column, a computed cell set by hand, a column
            deleted while a formula reads it, or a result `normalize` refuses. The message names the failing edit.
    """
    if not ops:
        raise ValidationFailed("Chưa có thao tác nào trên bảng.")
    if len(ops) > MAX_OPS:
        raise ValidationFailed(f"Tối đa {MAX_OPS} thao tác mỗi lần.")
    work = copy.deepcopy(ensure_ids(spec))
    notes: list[str] = []
    for number, op in enumerate(ops, 1):
        kind = op.get("op")
        handler = _OPS.get(kind)
        if handler is None:
            raise ValidationFailed(f"Thao tác {number}: '{kind}' không có (dùng {', '.join(OPS)}).")
        try:
            note = handler(work, op)
        except ValidationFailed as exc:
            raise ValidationFailed(f"Thao tác {number} ({kind}): {exc.message}") from None
        if note:
            notes.append(note)
    return normalize(work), notes


def _cells(spec: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Every cell keyed by ``(row id, column id)``; a section row's one cell by ``(row id, "")``."""
    ids = [leaf["id"] for leaf in leaves(spec)]
    out = {}
    for row in spec["rows"]:
        if row["type"] == "section":
            out[(row["id"], "")] = row["cells"][0]
        else:
            out.update({(row["id"], ids[i]): text for i, text in enumerate(row["cells"])})
    return out


def dropped_figures(old: dict[str, Any], new: dict[str, Any]) -> list[Decimal]:
    """The figures a change took out of a table: changed or removed cells whose figure the new table no longer holds anywhere.

    One-digit figures are left out: they are too common in text ("1.", "3 bộ") to tell a passage quoted them.

    Args:
        old: The spec before.
        new: The spec after.

    Returns:
        The figures, smallest first.
    """
    before, after = _cells(ensure_ids(old)), _cells(ensure_ids(new))
    still = {value for text in after.values() if (value := parse_number(text)) is not None}
    gone = set()
    for key, text in before.items():
        if after.get(key) == text:
            continue
        value = parse_number(text)
        if value is not None and sum(ch.isdigit() for ch in text) >= 2 and value not in still:
            gone.add(value)
    return sorted(gone)


# ----- layout -----
def header(spec: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """The heading rows of a table with the span of each cell.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        One row, or two when a column has sub-columns; a column without sub-columns then spans both rows. Each cell is
        ``{"text", "col", "colspan", "rowspan"}``, `col` being the index of its first leaf column.
    """
    two = any(c.get("children") for c in spec["columns"])
    top: list[dict[str, Any]] = []
    bottom: list[dict[str, Any]] = []
    col = 0
    for column in spec["columns"]:
        children = column.get("children") or []
        if children:
            top.append({"text": column["label"], "col": col, "colspan": len(children), "rowspan": 1})
            for child in children:
                bottom.append({"text": child["label"], "col": col, "colspan": 1, "rowspan": 1})
                col += 1
        else:
            top.append({"text": column["label"], "col": col, "colspan": 1, "rowspan": 2 if two else 1})
            col += 1
    return [top, bottom] if two else [top]


def aligns(spec: dict[str, Any]) -> list[str]:
    """The alignment of each leaf column.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        ``left``, ``center`` or ``right`` per leaf column: as written, else centred for the ordinal column ("TT"), for figures and
        for short values such as units ("Chiếc"), left for text.
    """
    out = []
    for index, leaf in enumerate(leaves(spec)):
        if leaf.get("align"):
            out.append(leaf["align"])
            continue
        values = [row["cells"][index] for row in spec["rows"] if row["type"] in ("row", "total") and row["cells"][index]]
        short = values and max(len(v) for v in values) <= 8
        figures = values and all(_NUMBER.match(v) for v in values)
        out.append("center" if leaf["label"].casefold() in _ORDINAL_LABELS or figures or short else "left")
    return out


def _longest_word(text: str, bold: bool) -> float:
    """Width in cm of the widest word of `text`, which no column can be narrower than."""
    return max((metrics.width_cm(word, TABLE_PT, bold=bold) for word in text.split()), default=0.0)


def _natural(spec: dict[str, Any]) -> list[tuple[float, float]]:
    """The narrowest and the comfortable width of each leaf column.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        ``(narrowest, comfortable)`` in cm per leaf column, cell padding included. Narrowest: its longest word. Comfortable: every
        cell on one line (up to 9 cm), and the heading on one line when it is two words, on two lines when longer.
    """
    out = []
    for index, leaf in enumerate(leaves(spec)):
        label = leaf["label"]
        cells = [(row["cells"][index], row["type"] in ("group", "total")) for row in spec["rows"] if row["type"] != "section"]
        narrow = max([_longest_word(label, True), *(_longest_word(c, bold) for c, bold in cells)])
        heading = metrics.width_cm(label, TABLE_PT, bold=True)
        wide = max([heading if len(label.split()) <= 2 else heading / 2 + 0.3,
                    *(min(metrics.width_cm(c, TABLE_PT, bold=bold), 9.0) for c, bold in cells)])
        out.append((narrow + CELL_PAD_CM, max(narrow, wide) + CELL_PAD_CM))
    return out


def landscape(spec: dict[str, Any]) -> bool:
    """Whether a table needs a landscape page.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        The spec's ``landscape`` when given; otherwise True when its columns cannot sit comfortably in the portrait text width
        (or it has eight leaf columns or more).
    """
    if spec.get("landscape") is not None:
        return bool(spec["landscape"])
    sizes = _natural(spec)
    return sum(n for n, _ in sizes) > PORTRAIT_CM or sum(w for _, w in sizes) > PORTRAIT_CM * 1.25 or len(sizes) >= 8


def widths(spec: dict[str, Any], room_cm: float) -> list[float]:
    """The width of each leaf column, filling the text width.

    Every column first gets its longest word; the rest of the room is shared by how much more each column needs to sit
    comfortably. Once all of them do, what is left widens the text columns (left-aligned), not the figures.

    Args:
        spec: A spec returned by `normalize`.
        room_cm: Text width of the page in cm.

    Returns:
        Widths in cm, left to right, summing to `room_cm`.
    """
    sizes = _natural(spec)
    narrow = [n for n, _ in sizes]
    if sum(narrow) >= room_cm:
        return [room_cm * n / sum(narrow) for n in narrow]
    want = [w - n for n, w in sizes]
    spare = room_cm - sum(narrow)
    if sum(want) > spare:
        return [n + spare * w / sum(want) for n, w in zip(narrow, want)]
    comfortable = [w for _, w in sizes]
    text = [w if align == "left" else 0.0 for w, align in zip(comfortable, aligns(spec))]
    share = text if sum(text) else comfortable
    extra = room_cm - sum(comfortable)
    return [w + extra * s / sum(share) for w, s in zip(comfortable, share)]


def fits(spec: dict[str, Any], room_cm: float) -> bool:
    """Whether every column can show its longest word within `room_cm` (the table is readable at that width)."""
    return sum(n for n, _ in _natural(spec)) <= room_cm


def summary(spec: dict[str, Any]) -> str:
    """One line naming a table, kept as the text of its block.

    The history, the style check and the assistant's view of the draft read this line instead of the cells.

    Args:
        spec: A spec returned by `normalize`.

    Returns:
        "Bảng: <leaf labels joined by ' | '> (<n> dòng)".
    """
    labels = " | ".join(leaf["label"] for leaf in leaves(spec))
    return f"Bảng: {labels} ({len(spec['rows'])} dòng)"


def blanks(spec: dict[str, Any]) -> int:
    """The number of cells still holding "…" (figures the user has to give, or that depend on one)."""
    return sum(1 for row in spec["rows"] for cell in row["cells"] if GAP in cell)
