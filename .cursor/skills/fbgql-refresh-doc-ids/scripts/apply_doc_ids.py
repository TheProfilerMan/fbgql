#!/usr/bin/env python3
"""Apply captured Facebook GraphQL doc_ids (+ provider vars) into fbgql config.py.

Usage:
  python apply_doc_ids.py --capture captured_queries.json --config src/fbgql/config.py

Only updates keys present in capture ``resolved``. Prints a before/after summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


LOGICAL = ("timeline", "group_feed", "comments", "replies")


def _load_capture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    resolved = data.get("resolved") or {}
    if not isinstance(resolved, dict) or not resolved:
        raise SystemExit(
            f"No resolved queries in {path}. Re-run: fbgql capture --out {path.name}"
        )
    return resolved


def _provider_subset(variables: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(variables, dict):
        return {}
    return {k: v for k, v in variables.items() if k.startswith("__relay_internal__")}


def _py_literal(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    # nested dicts/lists shouldn't appear in provider vars; fall back to json→python
    return json.dumps(value, ensure_ascii=False).replace("null", "None").replace(
        "true", "True"
    ).replace("false", "False")


def _format_dict_entries(d: dict[str, Any], indent: str = "    ") -> str:
    lines = []
    for k, v in d.items():
        lines.append(f'{indent}{json.dumps(k)}: {_py_literal(v)},')
    return "\n".join(lines)


def _replace_default_doc_ids(text: str, updates: dict[str, str]) -> tuple[str, list[str]]:
    notes: list[str] = []
    for name, new_id in updates.items():
        pattern = re.compile(
            rf'(["\']{re.escape(name)}["\']\s*:\s*)["\'](\d+)["\']',
            re.MULTILINE,
        )

        def _sub(m: re.Match[str], _new: str = new_id, _name: str = name) -> str:
            old = m.group(2)
            if old == _new:
                notes.append(f"doc_id.{_name}: unchanged ({_new})")
            else:
                notes.append(f"doc_id.{_name}: {old} → {_new}")
            return f'{m.group(1)}"{_new}"'

        new_text, n = pattern.subn(_sub, text, count=1)
        if n == 0:
            notes.append(f"doc_id.{name}: NOT FOUND in config (skipped)")
        else:
            text = new_text
    return text, notes


def _replace_named_dict(
    text: str, const_name: str, new_body: dict[str, Any]
) -> tuple[str, str]:
    """Replace the interior of ``CONST_NAME: dict = { ... }`` while keeping outer braces."""
    if not new_body:
        return text, f"{const_name}: no provider vars in capture (skipped)"

    # Match from assignment through the closing brace at indent 0 of the dict.
    pattern = re.compile(
        rf"({re.escape(const_name)}:\s*dict\s*=\s*\{{)(.*?)(\n\}})",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return text, f"{const_name}: NOT FOUND (skipped)"

    # Preserve non-provider keys already in the block; refresh __relay_internal__* from capture.
    existing: dict[str, Any] = {}
    # Pull simple "key": value pairs from the old block for non-relay keys.
    for km in re.finditer(
        r'^\s*("(?:\\.|[^"])+"|\'(?:\\.|[^\'])+\')\s*:\s*(.+?),?\s*$',
        m.group(2),
        re.MULTILINE,
    ):
        key = json.loads(km.group(1).replace("'", '"')) if km.group(1).startswith("'") else json.loads(km.group(1))
        raw_val = km.group(2).rstrip(",")
        if key.startswith("__relay_internal__"):
            continue
        existing[key] = raw_val  # keep raw python expr for non-relay keys

    # Rebuild: keep original non-relay lines order from existing raw, then providers.
    # Simpler + safer: if const is UFI_COMMENT_PROVIDER_VARS, replace entirely with providers.
    if const_name == "UFI_COMMENT_PROVIDER_VARS":
        interior = "\n" + _format_dict_entries(new_body) + "\n"
        text = text[: m.start()] + m.group(1) + interior + m.group(3) + text[m.end() :]
        return text, f"{const_name}: replaced {len(new_body)} provider key(s)"

    # For TIMELINE / GROUP_FEED bases: swap only __relay_internal__ lines; keep static keys.
    old_interior = m.group(2)
    # Drop old provider lines.
    kept_lines = []
    for line in old_interior.splitlines():
        if "__relay_internal__" in line:
            continue
        kept_lines.append(line)
    # Ensure trailing comma structure: strip empty trailing lines, append providers.
    while kept_lines and kept_lines[-1].strip() == "":
        kept_lines.pop()
    provider_block = _format_dict_entries(new_body)
    new_interior = "\n".join(kept_lines)
    if new_interior and not new_interior.endswith("\n"):
        new_interior += "\n"
    if not new_interior.startswith("\n"):
        new_interior = "\n" + new_interior
    new_interior = new_interior.rstrip("\n") + "\n" + provider_block + "\n"
    text = text[: m.start()] + m.group(1) + new_interior + m.group(3) + text[m.end() :]
    return text, f"{const_name}: refreshed {len(new_body)} provider key(s)"


def apply(capture_path: Path, config_path: Path, *, dry_run: bool = False) -> int:
    resolved = _load_capture(capture_path)
    text = config_path.read_text(encoding="utf-8")
    notes: list[str] = []

    doc_updates = {
        name: str(resolved[name]["doc_id"])
        for name in LOGICAL
        if name in resolved and resolved[name].get("doc_id")
    }
    if not doc_updates:
        raise SystemExit("resolved entries lack doc_id fields")

    text, doc_notes = _replace_default_doc_ids(text, doc_updates)
    notes.extend(doc_notes)

    # Provider vars
    if "timeline" in resolved:
        text, note = _replace_named_dict(
            text, "TIMELINE_VARIABLES_BASE", _provider_subset(resolved["timeline"].get("variables"))
        )
        notes.append(note)
    if "group_feed" in resolved:
        text, note = _replace_named_dict(
            text,
            "GROUP_FEED_VARIABLES_BASE",
            _provider_subset(resolved["group_feed"].get("variables")),
        )
        notes.append(note)

    ufi_src = None
    for name in ("comments", "replies"):
        if name in resolved:
            ufi_src = _provider_subset(resolved[name].get("variables"))
            if ufi_src:
                break
    if ufi_src:
        text, note = _replace_named_dict(text, "UFI_COMMENT_PROVIDER_VARS", ufi_src)
        notes.append(note)
    else:
        notes.append("UFI_COMMENT_PROVIDER_VARS: no comment/reply providers in capture (skipped)")

    print("Apply plan:")
    for n in notes:
        print(f"  • {n}")
    missing = [n for n in LOGICAL if n not in resolved]
    if missing:
        print(f"  • NOT in capture (left unchanged): {', '.join(missing)}")

    if dry_run:
        print("dry-run: no files written")
        return 0

    config_path.write_text(text, encoding="utf-8")
    print(f"Wrote {config_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, default=Path("captured_queries.json"))
    ap.add_argument("--config", type=Path, default=Path("src/fbgql/config.py"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.capture.exists():
        raise SystemExit(f"capture file not found: {args.capture}")
    if not args.config.exists():
        raise SystemExit(f"config file not found: {args.config}")
    return apply(args.capture, args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
