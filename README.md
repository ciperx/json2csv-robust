# json2csv-robust

Dependency-free (stdlib-only) `json2csv.py` that converts JSON → CSV.

## What it does
- Flattens nested JSON objects/arrays into stable CSV columns.
- Handles arrays-of-objects and single objects.
- utf-8 output, deterministic column order.
- Streaming-safe for large inputs (generator-based row emission).

## Tests
`python -m pytest -q` — includes round-trip and edge-case coverage.

## Usage
```bash
python3 json2csv.py input.json -o output.csv
```
