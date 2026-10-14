from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source-v1.2"
REPORT_PATH = ROOT / "I18N_INVENTORY.md"
HANGUL_RE = re.compile(r"[가-힣]")

USER_FACING_MARKERS = (
    "QLabel(", "QPushButton(", "QCheckBox(", "QComboBox(", "QToolButton(",
    "QMessageBox", "QFileDialog", "setText(", "setToolTip(",
    "setPlaceholderText(", "setWindowTitle(", "setStatusTip(", "setTitle(",
    "addItem(", "addItems(", "addAction(", "setHeaderLabels(",
    "setHorizontalHeaderLabels(", "setVerticalHeaderLabels(",
    "warnings.append(", "raise SaveLayoutError", "raise CarDatabaseError",
    "raise GameNavigationError", "raise TuneDataError", "raise ValueError",
)

DATA_PATTERN_MARKERS = (
    "re.compile", "re.search", "pattern", "patterns", "_first_line_value",
    "SaveDescription", "운전한 시간", "경험치", "차고",
)


def _docstring_lines(tree: ast.AST) -> set[int]:
    result: set[int] = set()
    nodes = [tree]
    nodes.extend(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    for node in nodes:
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            result.add(first.lineno)
    return result


def _normalize(text: str) -> str:
    return " ".join(text.replace("`", "\\`").split())


def _category(line: str, lineno: int, doc_lines: set[int]) -> str:
    if lineno in doc_lines:
        return "docstring"
    if any(marker in line for marker in DATA_PATTERN_MARKERS):
        return "data/pattern"
    if any(marker in line for marker in USER_FACING_MARKERS):
        return "user-facing"
    return "review"


def collect() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text, filename=str(path))
        doc_lines = _docstring_lines(tree)
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if not HANGUL_RE.search(node.value):
                continue
            lineno = getattr(node, "lineno", 0) or 0
            source_line = lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else ""
            rows.append(
                {
                    "file": relative,
                    "line": lineno,
                    "category": _category(source_line, lineno, doc_lines),
                    "text": _normalize(node.value),
                    "source": source_line,
                }
            )
    rows.sort(key=lambda x: (str(x["file"]), int(x["line"]), str(x["text"])))
    return rows


def main() -> None:
    rows = collect()
    by_file: Counter[str] = Counter(str(row["file"]) for row in rows)
    by_cat: Counter[str] = Counter(str(row["category"]) for row in rows)
    unique = {(str(row["file"]), int(row["line"]), str(row["text"])) for row in rows}

    out: list[str] = [
        "# FH6 Assistant v1.2 i18n inventory",
        "",
        "Generated mechanically from `source-v1.2/**/*.py` by finding Python string literals containing Hangul.",
        "Tests are excluded. Classification is heuristic and must be reviewed before replacing strings.",
        "",
        "## Summary",
        "",
        f"- Hangul string literal occurrences: {len(rows)}",
        f"- Unique file/line/text occurrences: {len(unique)}",
        f"- Files containing Hangul literals: {len(by_file)}",
        "",
        "### By category",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category in ("user-facing", "review", "data/pattern", "docstring"):
        out.append(f"| {category} | {by_cat.get(category, 0)} |")

    out.extend([
        "",
        "### By file",
        "",
        "| File | Count |",
        "|---|---:|",
    ])
    for file_name, count in sorted(by_file.items(), key=lambda item: (-item[1], item[0])):
        out.append(f"| `{file_name}` | {count} |")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["file"])].append(row)

    out.extend(["", "## Occurrences", ""])
    for file_name in sorted(grouped):
        out.extend([
            f"### `{file_name}`",
            "",
            "| Line | Category | Literal |",
            "|---:|---|---|",
        ])
        for row in grouped[file_name]:
            literal = str(row["text"]).replace("|", "\\|")
            if len(literal) > 180:
                literal = literal[:177] + "..."
            out.append(f"| {row['line']} | {row['category']} | `{literal}` |")
        out.append("")

    REPORT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Occurrences: {len(rows)}")
    print("By category:", dict(by_cat))
    print("By file:", dict(by_file))


if __name__ == "__main__":
    main()
