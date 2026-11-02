"""Tests for json2csv. Run with: python -m pytest -q"""

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json2csv  # noqa: E402


def run_cli(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "json2csv.py"), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def read_csv(path, encoding="utf-8"):
    with open(path, "r", encoding=encoding, newline="") as handle:
        return list(csv.reader(handle))


# ---------------------------------------------------------------- unit level

def test_basic_conversion():
    headers, rows = json2csv.convert([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    assert headers == ["a", "b"]
    assert rows == [["1", "x"], ["2", "y"]]


def test_missing_keys_become_empty_string():
    data = [{"a": 1, "b": 2}, {"a": 3}, {"b": 4, "c": 5}]
    headers, rows = json2csv.convert(data)
    assert headers == ["a", "b", "c"]
    assert rows == [["1", "2", ""], ["3", "", ""], ["", "4", "5"]]


def test_column_order_is_union_in_first_seen_order():
    data = [{"z": 1}, {"a": 2}, {"z": 3, "m": 4}]
    headers, _ = json2csv.convert(data)
    assert headers == ["z", "a", "m"]


def test_forced_columns_fix_order_and_selection():
    data = [{"a": 1, "b": 2, "c": 3}]
    headers, rows = json2csv.convert(data, columns=["c", "a"])
    assert headers == ["c", "a"]
    assert rows == [["3", "1"]]


def test_nested_objects_are_json_without_flatten():
    headers, rows = json2csv.convert([{"meta": {"x": 1}}])
    assert headers == ["meta"]
    assert rows == [['{"x":1}']]


def test_flatten_uses_dotted_keys():
    data = [{"id": 1, "user": {"name": "Ann", "address": {"city": "Oslo"}}}]
    headers, rows = json2csv.convert(data, flatten=True)
    assert headers == ["id", "user.name", "user.address.city"]
    assert rows == [["1", "Ann", "Oslo"]]


def test_lists_are_json_encoded():
    headers, rows = json2csv.convert([{"tags": ["a", "b"], "n": 1}])
    assert rows == [['["a","b"]', "1"]]


def test_unicode_is_preserved():
    headers, rows = json2csv.convert([{"name": "José 日本 🚀"}])
    assert rows == [["José 日本 🚀"]]


def test_types_rendered_sensibly():
    headers, rows = json2csv.convert(
        [{"t": True, "f": False, "n": None, "i": 7, "fl": 1.5}]
    )
    assert headers == ["t", "f", "n", "i", "fl"]
    assert rows == [["true", "false", "", "7", "1.5"]]


def test_empty_array_gives_no_columns():
    headers, rows = json2csv.convert([])
    assert headers == []
    assert rows == []


def test_empty_array_with_forced_columns():
    headers, rows = json2csv.convert([], columns=["a", "b"])
    assert headers == ["a", "b"]
    assert rows == []


@pytest.mark.parametrize("bad", [{"a": 1}, "nope", 42, None])
def test_non_array_top_level_raises(bad):
    with pytest.raises(json2csv.ConversionError):
        json2csv.convert(bad)


def test_non_object_element_raises():
    with pytest.raises(json2csv.ConversionError, match="element 1"):
        json2csv.convert([{"a": 1}, "oops"])


# ---------------------------------------------------------------- CLI level

def test_cli_writes_file(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text(json.dumps([{"a": 1, "b": "x"}, {"a": 2}]), encoding="utf-8")

    result = run_cli([str(src), "-o", str(out)])
    assert result.returncode == 0, result.stderr
    assert read_csv(out) == [["a", "b"], ["1", "x"], ["2", ""]]


def test_cli_stdout_by_default(tmp_path):
    src = tmp_path / "in.json"
    src.write_text('[{"a": 1}]', encoding="utf-8")
    result = run_cli([str(src)])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "a\n1\n"


def test_cli_quotes_embedded_delimiters_and_quotes(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    value = 'He said "hi", then left'
    src.write_text(json.dumps([{"a": value, "b": 1}]), encoding="utf-8")
    assert run_cli([str(src), "-o", str(out)]).returncode == 0
    rows = read_csv(out)
    assert rows[1][0] == value
    assert '"' in out.read_text(encoding="utf-8")


def test_cli_delimiter_semicolon(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text('[{"a": "x;y", "b": 2}]', encoding="utf-8")
    result = run_cli([str(src), "-o", str(out), "--delimiter", ";"])
    assert result.returncode == 0, result.stderr
    assert read_csv(out) != []
    with open(out, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows == [["a", "b"], ["x;y", "2"]]


def test_cli_tab_delimiter_alias(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text('[{"a": 1, "b": 2}]', encoding="utf-8")
    assert run_cli([str(src), "-o", str(out), "--delimiter", "\\t"]).returncode == 0
    assert out.read_text(encoding="utf-8") == "a\tb\n1\t2\n"


def test_cli_bom(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text('[{"a": 1}]', encoding="utf-8")
    assert run_cli([str(src), "-o", str(out), "--bom"]).returncode == 0
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")


def test_cli_unicode_file_roundtrip(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text(json.dumps([{"nama": "Ünïcode ☃"}], ensure_ascii=False),
                   encoding="utf-8")
    assert run_cli([str(src), "-o", str(out)]).returncode == 0
    assert read_csv(out) == [["nama"], ["Ünïcode ☃"]]


def test_cli_empty_array_header_only_with_columns(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text("[]", encoding="utf-8")
    result = run_cli([str(src), "-o", str(out), "--columns", "a,b"])
    assert result.returncode == 0, result.stderr
    assert out.read_text(encoding="utf-8") == "a,b\n"


def test_cli_empty_array_without_columns_is_empty_file(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text("[]", encoding="utf-8")
    result = run_cli([str(src), "-o", str(out)])
    assert result.returncode == 0
    assert out.read_text(encoding="utf-8") == ""
    assert "no columns" in result.stderr


def test_cli_invalid_json_exit_code_2(tmp_path):
    src = tmp_path / "bad.json"
    src.write_text('[{"a": 1,}', encoding="utf-8")
    result = run_cli([str(src)])
    assert result.returncode == 2
    assert "invalid JSON" in result.stderr
    assert "line 1" in result.stderr


def test_cli_missing_file_exit_code_2(tmp_path):
    result = run_cli([str(tmp_path / "nope.json")])
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_cli_non_array_exit_code_2(tmp_path):
    src = tmp_path / "obj.json"
    src.write_text('{"a": 1}', encoding="utf-8")
    result = run_cli([str(src)])
    assert result.returncode == 2
    assert "array of objects" in result.stderr


def test_cli_flatten_and_columns(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text(
        json.dumps([{"id": 1, "u": {"name": "A", "geo": {"cc": "NO"}}}]),
        encoding="utf-8",
    )
    result = run_cli([str(src), "-o", str(out), "--flatten",
                      "--columns", "u.geo.cc,id,u.name"])
    assert result.returncode == 0, result.stderr
    assert read_csv(out) == [["u.geo.cc", "id", "u.name"], ["NO", "1", "A"]]


def test_cli_bad_delimiter_exit_code_2(tmp_path):
    src = tmp_path / "in.json"
    src.write_text("[]", encoding="utf-8")
    result = run_cli([str(src), "--delimiter", "ab"])
    assert result.returncode == 2
    assert "delimiter" in result.stderr


def test_cli_newlines_in_values_roundtrip(tmp_path):
    src = tmp_path / "in.json"
    out = tmp_path / "out.csv"
    src.write_text(json.dumps([{"a": "line1\nline2"}]), encoding="utf-8")
    assert run_cli([str(src), "-o", str(out)]).returncode == 0
    assert read_csv(out) == [["a"], ["line1\nline2"]]
