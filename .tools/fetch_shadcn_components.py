#!/usr/bin/env python3
"""
Bulk-fetch shadcn/ui radix-nova style components from the public registry.
Saves raw TSX to web/app/components/ui/<name>.tsx and updates lib/utils.ts.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

REGISTRY = "https://ui.shadcn.com/r/styles/radix-nova"
ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "web" / "app" / "components" / "ui"
LIB_DIR = ROOT / "web" / "app" / "lib"


# Map of registry name -> local file name (some components ship multiple files,
# those are merged into a single module below)
COMPONENTS: list[str] = [
    "button",
    "input",
    "input-group",
    "label",
    "card",
    "badge",
    "dialog",
    "sheet",
    "dropdown-menu",
    "table",
    "separator",
    "avatar",
    "tooltip",
    "tabs",
    "scroll-area",
    "progress",
    "skeleton",
    "switch",
    "popover",
    "select",
    "textarea",
    "checkbox",
    "alert-dialog",
    "breadcrumb",
    "command",
    "sonner",
    "spinner",
    "empty",
    "field",
    "form",
    "item",
    "kbd",
    "button-group",
    "data-table",
    "chart",
]


def _fetch(name: str) -> dict[str, Any]:
    url = f"{REGISTRY}/{name}.json"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def _strip_registry_paths(content: str) -> str:
    """Rewrite `@/registry/radix-nova/lib/...` -> shadcn alias local imports.
    The registry prefixes paths with `@/registry/radix-nova/lib/utils`. We'll
    replace with `~/lib/utils` which matches our `components.json` alias.
    """
    content = re.sub(
        r"@/registry/radix-nova/lib/utils",
        "~/lib/utils",
        content,
    )
    content = re.sub(
        r"@/registry/radix-nova/ui/([^'\"]+)",
        r"~/components/ui/\1",
        content,
    )
    # registry uses `import type * as React from "react"` on first line in some
    # files; let TS handle that natively.
    return content


def write_component(name: str, dry: bool = False) -> tuple[int, int]:
    """Fetch the registry item and write the component file(s). Return (files, lines)."""
    item = _fetch(name)
    files = item.get("files", [])
    if not isinstance(files, list) or not files:
        return (0, 0)

    written = 0
    total_lines = 0
    for f in files:
        rel = f.get("path", "")
        if not rel or "content" not in f:
            continue
        # rel looks like "registry/radix-nova/ui/input.tsx" -> local "input.tsx"
        local_name = Path(rel).name
        target = UI_DIR / local_name
        body = _strip_registry_paths(f["content"])
        total_lines += body.count("\n")
        if not dry:
            UI_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        written += 1
    return (written, total_lines)


def main(argv: list[str]) -> int:
    UI_DIR.mkdir(parents=True, exist_ok=True)
    LIB_DIR.mkdir(parents=True, exist_ok=True)

    dry = "--dry-run" in argv
    filter_name = next((a for a in argv if not a.startswith("-")), None)

    total_files = 0
    total_lines = 0
    summary: list[tuple[str, int, int]] = []
    for name in COMPONENTS:
        try:
            files, lines = write_component(name, dry=dry)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] {name}: {exc}")
            continue
        if filter_name and filter_name != name:
            continue
        summary.append((name, files, lines))
        total_files += files
        total_lines += lines
    print(f"--- {len(summary)} components, {total_files} files, {total_lines} lines ---")
    for n, f, l in summary:
        print(f"  {n}: {f} files / {l} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
