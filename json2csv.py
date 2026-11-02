#!/usr/bin/env python3
"""json2csv - convert a JSON array of flat objects into CSV.

Standard library only. See README.md for usage.

Exit codes:
    0  success
    2  invalid input (unreadable file, invalid JSON, wrong JSON shape, bad args)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import Any, Dict, Iterable, List, Sequence, Tuple

__version__ = "1.0.0"

EXIT_OK = 0
EXIT_INPUT_ERROR = 2


class ConversionError(Exception):
    """Raised for any user-facing input problem (mapped to exit code 2)."""


# --------------------------------------------------------------------------
# Value handling
# --------------------------------------------------------------------------

def _scalar_to_text(value: Any) -> str:
    """Render a JSON scalar as a CSV cell.

    None -> empty string, booleans -> true/false, numbers -> decimal repr,
    everything else is serialised as compact JSON (unicode preserved).
    """
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def _flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dicts into dotted keys. Lists stay as JSON values."""
    flat: Dict[str, Any] = {}
    for key, value in obj.items():
        name = "%s.%s" % (prefix, key) if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        else:
            flat[name] = value
    return flat


def normalise_rows(
    data: Sequence[Any], flatten: bool
) -> List[Dict[str, Any]]:
    """Validate the top-level array and optionally flatten each element."""
    if not isinstance(data, list):
        raise ConversionError(
            "top-level JSON value must be an array of objects, got %s"
            % type(data).__name__
        )

    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ConversionError(
                "array element %d is %s, expected an object"
                % (index, type(item).__name__)
            )
        rows.append(_flatten(item) if flatten else item)
    return rows


def collect_columns(
    rows: Iterable[Dict[str, Any]], forced: Sequence[str] | None = None
) -> List[str]:
    """Return columns: forced order if given, else union of keys first-seen."""
    if forced is not None:
        return list(forced)

    seen: Dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(str(key), None)
    return list(seen)


def convert(
    data: Any,
    *,
    columns: Sequence[str] | None = None,
    flatten: bool = False,
    delimiter: str = ",",
) -> Tuple[List[str], List[List[str]]]:
    """Convert parsed JSON into (header, rows of strings)."""
    rows = normalise_rows(data, flatten)
    headers = collect_columns(rows, columns)
    out: List[List[str]] = []
    for row in rows:
        out.append([_scalar_to_text(row.get(h)) for h in headers])
    return headers, out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _parse_delimiter(raw: str) -> str:
    aliases = {"\\t": "\t", "tab": "\t", "\\n": "\n"}
    value = aliases.get(raw, raw)
    if len(value) != 1:
        raise ConversionError(
            "delimiter must be exactly one character (got %r)" % raw
        )
    return value


def _parse_columns(raw: str) -> List[str]:
    cols = [c.strip() for c in raw.split(",")]
    cols = [c for c in cols if c]
    if not cols:
        raise ConversionError("--columns must contain at least one column name")
    if len(set(cols)) != len(cols):
        raise ConversionError("--columns contains duplicate column names")
    return cols


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="json2csv",
        description="Convert a JSON array of objects into a CSV file.",
    )
    parser.add_argument("input", help="path to the input JSON file ('-' for stdin)")
    parser.add_argument(
        "-o", "--output", default=None,
        help="output CSV path (default: stdout)",
    )
    parser.add_argument(
        "--columns", default=None,
        help="comma-separated column names; fixes both order and selection",
    )
    parser.add_argument(
        "--flatten", action="store_true",
        help="flatten nested objects into dotted column names",
    )
    parser.add_argument(
        "--bom", action="store_true",
        help="write a UTF-8 BOM (helps Excel detect the encoding)",
    )
    parser.add_argument(
        "--delimiter", default=",", metavar="CHAR",
        help="field delimiter, one character, e.g. ';' or '\\t' (default: ',')",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__,
    )
    return parser


def _read_input(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.buffer.read().decode("utf-8-sig")
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except FileNotFoundError:
        raise ConversionError("input file not found: %s" % path)
    except IsADirectoryError:
        raise ConversionError("input path is a directory: %s" % path)
    except UnicodeDecodeError as exc:
        raise ConversionError("input file is not valid UTF-8: %s" % exc)
    except OSError as exc:
        raise ConversionError("cannot read input file %s: %s" % (path, exc))


def _render(headers: List[str], rows: List[List[str]], delimiter: str) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
    )
    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        delimiter = _parse_delimiter(args.delimiter)
        forced = _parse_columns(args.columns) if args.columns is not None else None

        text = _read_input(args.input)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConversionError(
                "invalid JSON in %s: %s (line %d, column %d)"
                % (args.input, exc.msg, exc.lineno, exc.colno)
            )

        headers, rows = convert(
            data, columns=forced, flatten=args.flatten, delimiter=delimiter
        )
        body = _render(headers, rows, delimiter)
    except ConversionError as exc:
        print("json2csv: error: %s" % exc, file=sys.stderr)
        return EXIT_INPUT_ERROR

    if not headers:
        print(
            "json2csv: warning: no columns discovered (empty input); "
            "wrote an empty CSV",
            file=sys.stderr,
        )

    encoding = "utf-8-sig" if args.bom else "utf-8"
    if args.output:
        try:
            with open(args.output, "w", encoding=encoding, newline="") as handle:
                handle.write(body)
        except OSError as exc:
            print("json2csv: error: cannot write %s: %s" % (args.output, exc),
                  file=sys.stderr)
            return EXIT_INPUT_ERROR
    else:
        data_bytes = body.encode(encoding)
        sys.stdout.buffer.write(data_bytes)
        sys.stdout.buffer.flush()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
