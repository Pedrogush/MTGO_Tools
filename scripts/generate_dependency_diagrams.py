#!/usr/bin/env python3
"""Regenerate dependency-graph artifacts under ``docs/diagrams/``.

Walks every ``*.py`` file under the internal source packages, extracts import
edges via ``ast`` (never actually importing anything, so wxPython and other
heavy/optional deps don't matter), filters edges to internal modules only,
then collapses module names to depths 1 and 2 to produce two granularity
levels (top-level packages and one-level-deeper modules — level 3 was dropped
as too dense to visually parse).

Outputs (all under ``docs/diagrams/``):

- ``graph.json``                       — canonical, sorted edge sets + metadata
- ``dependencies_level_<N>.dot``       — Graphviz source (gitignored)
- ``dependencies_level_<N>.svg``       — rendered diagram (committed)

Usage::

    python scripts/generate_dependency_diagrams.py            # regenerate all
    python scripts/generate_dependency_diagrams.py --check    # exit 1 if drift
    python scripts/generate_dependency_diagrams.py --json-only  # skip SVG render

The ``--check`` mode compares only the ``edges`` section of ``graph.json`` and
is stdlib-only — CI doesn't need ``pydeps``, ``graphviz``, or wxPython. SVG
rendering needs the ``dot`` binary on PATH (``apt install graphviz`` on Linux).
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Source dirs whose imports we chart. ``tests`` and ``scripts`` are intentionally
# excluded — they depend on everything and would create noise.
INTERNAL_PACKAGES = (
    "automation",
    "controllers",
    "navigators",
    "repositories",
    "services",
    "utils",
    "widgets",
)
TOP_LEVEL_MODULES = ("main",)  # standalone .py files at repo root worth charting
GRAPH_LEVELS = (1, 2)
DIAGRAMS_DIR = "docs/diagrams"
GRAPH_FILE = "graph.json"


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _repo_root() -> Path:
    return Path(_git("rev-parse", "--show-toplevel"))


def module_name_for(rel_path: Path) -> str:
    """Convert ``services/card_data/fetcher.py`` to ``services.card_data.fetcher``.

    ``__init__.py`` becomes the package itself (``services.card_data``).
    """
    parts = list(rel_path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def discover_modules(root: Path) -> dict[str, Path]:
    """Map every internal module's dotted name to its source file."""
    modules: dict[str, Path] = {}
    for pkg in INTERNAL_PACKAGES:
        pkg_dir = root / pkg
        if not pkg_dir.is_dir():
            continue
        for py in pkg_dir.rglob("*.py"):
            rel = py.relative_to(root)
            modules[module_name_for(rel)] = py
    for top in TOP_LEVEL_MODULES:
        candidate = root / f"{top}.py"
        if candidate.is_file():
            modules[top] = candidate
    return modules


def is_internal(module: str) -> bool:
    top = module.split(".", 1)[0]
    return top in INTERNAL_PACKAGES or top in TOP_LEVEL_MODULES


def _resolve_relative(source_file: Path, root: Path, level: int, module: str | None) -> str | None:
    """Resolve ``from .x import …`` against the source file's directory.

    Relative imports are anchored to the *directory* containing the source file
    (which is the same as the package the module belongs to, whether the file
    is ``__init__.py`` or a regular submodule). ``level=1`` means "current
    package," ``level=2`` means "parent," and so on — climbing ``level - 1``
    directories from the source's parent.
    """
    source_dir_parts = list(source_file.parent.relative_to(root).parts)
    climb = level - 1
    if climb > len(source_dir_parts):
        return None  # malformed: over-climbed
    base_parts = source_dir_parts[: len(source_dir_parts) - climb] if climb else source_dir_parts
    if module:
        base_parts = base_parts + module.split(".")
    return ".".join(base_parts) if base_parts else None


def extract_edges(source_file: Path, source_module: str, root: Path, all_modules: set[str]) -> set[tuple[str, str]]:
    """Return the set of (source_module, target_module) edges from this file."""
    try:
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    edges: set[tuple[str, str]] = set()

    def emit(target: str | None) -> None:
        if not target or target == source_module or not is_internal(target):
            return
        edges.add((source_module, target))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # ``import a.b.c, x.y`` → targets are a.b.c and x.y
            for alias in node.names:
                emit(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                base = _resolve_relative(source_file, root, node.level, node.module)
            else:
                base = node.module
            if not base:
                continue
            # For ``from base import name``, ``base.name`` might be a submodule
            # (real edge target) or an attribute (then base is the target).
            for alias in node.names:
                if alias.name == "*":
                    emit(base)
                    continue
                candidate = f"{base}.{alias.name}"
                emit(candidate if candidate in all_modules else base)

    return edges


def collapse_to_level(edges: set[tuple[str, str]], level: int) -> set[tuple[str, str]]:
    """Truncate both endpoints of every edge to ``level`` dotted components."""
    collapsed: set[tuple[str, str]] = set()
    for src, dst in edges:
        s = ".".join(src.split(".")[:level])
        d = ".".join(dst.split(".")[:level])
        if s and d and s != d:
            collapsed.add((s, d))
    return collapsed


def build_graph(root: Path) -> dict[str, list[list[str]]]:
    """Return ``{level_N: [[src, dst], ...]}`` with edges sorted for stability."""
    modules = discover_modules(root)
    all_module_names = set(modules.keys())

    raw_edges: set[tuple[str, str]] = set()
    for module_name, source_file in modules.items():
        raw_edges |= extract_edges(source_file, module_name, root, all_module_names)

    out: dict[str, list[list[str]]] = {}
    for level in GRAPH_LEVELS:
        collapsed = collapse_to_level(raw_edges, level)
        out[f"level_{level}"] = sorted([s, d] for s, d in collapsed)
    return out


def build_payload(root: Path) -> dict:
    edges = build_graph(root)
    commit = _git("rev-parse", "HEAD", cwd=root)
    return {
        "edges": edges,
        "metadata": {
            "commit": commit,
            "commit_date": _git("show", "-s", "--format=%cI", "HEAD", cwd=root),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "internal_packages": list(INTERNAL_PACKAGES),
            "top_level_modules": list(TOP_LEVEL_MODULES),
        },
    }


# ---------- Graphviz emission -------------------------------------------------

# Stable colour palette per top-level package. Anything not listed falls
# through to a neutral grey.
PACKAGE_COLOURS = {
    "controllers": "#ff9999",
    "services": "#99ccff",
    "repositories": "#99ff99",
    "widgets": "#ffcc99",
    "utils": "#cc99ff",
    "navigators": "#ffff99",
    "automation": "#ffb3d9",
    "main": "#d9d9d9",
}


def node_colour(name: str) -> str:
    return PACKAGE_COLOURS.get(name.split(".", 1)[0], "#e0e0e0")


# Layered "spine + sidecars" layout. Each row is a rank in the rendered diagram;
# layers in the same row sit side-by-side (sidecars). The spine (linear flow
# through the request path) is enforced via invisible ordering edges.
LAYER_RANKS: tuple[tuple[str, ...], ...] = (
    ("main",),
    ("widgets", "automation"),
    ("controllers",),
    ("services",),
    ("repositories", "navigators"),
    ("utils",),
)
SPINE = ("main", "widgets", "controllers", "services", "repositories", "utils")
CYCLE_EDGE_COLOUR = "#cc3333"
# Columns per cluster grid at level 2. 3 keeps the biggest cluster (services,
# 14 modules) at ~5 rows — close to square. Larger values produce wider
# clusters, smaller produce taller; 3 hits the best aspect ratio empirically.
CLUSTER_COLUMNS = 3


def _top_layer(module: str) -> str:
    return module.split(".", 1)[0]


def detect_cycle_edges(edges: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Return edges whose endpoints share a strongly-connected component of size > 1.

    Catches every edge participating in any cycle, not just 2-cycles. Uses an
    iterative Tarjan to stay safe on larger graphs.
    """
    nodes: set[str] = {n for e in edges for n in e}
    adj: dict[str, list[str]] = defaultdict(list)
    for s, d in edges:
        adj[s].append(d)

    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[set[str]] = []
    counter = 0

    def strongconnect(root: str) -> None:
        nonlocal counter
        work: list[tuple[str, int]] = [(root, 0)]
        index_of[root] = lowlink[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, i = work[-1]
            succs = adj[node]
            if i < len(succs):
                work[-1] = (node, i + 1)
                nxt = succs[i]
                if nxt not in index_of:
                    index_of[nxt] = lowlink[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[nxt])
            else:
                work.pop()
                if lowlink[node] == index_of[node]:
                    component: set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.add(w)
                        if w == node:
                            break
                    sccs.append(component)
                if work:
                    parent, _ = work[-1]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

    for n in nodes:
        if n not in index_of:
            strongconnect(n)

    node_to_scc: dict[str, int] = {}
    for idx, comp in enumerate(sccs):
        for n in comp:
            node_to_scc[n] = idx
    return {
        (s, d)
        for s, d in edges
        if node_to_scc.get(s) == node_to_scc.get(d) and len(sccs[node_to_scc[s]]) > 1
    }


def filter_edges_for_display(
    edges: list[list[str]], *, level: int, excluded: frozenset[str]
) -> list[tuple[str, str]]:
    """Apply visual filters F1 (drop ``__init__`` re-exports), F4 (drop intra-layer
    edges at level >= 2), and F5 (drop edges touching an excluded layer).

    The committed ``graph.json`` keeps every edge — filtering only affects how
    SVGs are drawn, so the CI freshness gate stays stable.
    """
    out: list[tuple[str, str]] = []
    for s, d in edges:
        if _top_layer(s) in excluded or _top_layer(d) in excluded:
            continue
        if level >= 2:
            # F1: a → a.submodule re-exports come from package __init__.py and
            # don't carry architectural information the node list doesn't already.
            if d.startswith(s + "."):
                continue
            # F4: same-layer edges are interior wiring, not cross-layer flow.
            if _top_layer(s) == _top_layer(d):
                continue
        out.append((s, d))
    return out


def _quote(name: str) -> str:
    return f'"{name}"'


def render_dot_layered(
    level: int, edges: list[tuple[str, str]], cycle_edges: set[tuple[str, str]]
) -> str:
    """Emit dot source with spine + sidecar rank constraints.

    - Level 1: one node per layer, ranks enforced directly on nodes.
    - Level >= 2: each layer wrapped in a ``cluster_<layer>`` subgraph;
      same-rank constraints applied to representative nodes inside clusters.
    """
    nodes = sorted({n for e in edges for n in e})
    by_layer: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        by_layer[_top_layer(n)].append(n)
    for v in by_layer.values():
        v.sort()

    lines = [
        f'digraph "Dependencies — level {level}" {{',
        '  rankdir=TB;',
        '  compound=true;',
        '  newrank=true;',
        '  concentrate=true;',
        '  graph [fontname="Helvetica", labelloc="t", ranksep=0.4, nodesep=0.25];',
        f'  label="Dependencies — level {level}  (red = participates in a cycle)";',
        '  node  [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
        '  edge  [color="#555555", arrowsize=0.7];',
        '',
    ]

    if level == 1:
        for layer in nodes:
            lines.append(f'  "{layer}" [fillcolor="{node_colour(layer)}"];')
        lines.append('')
        for rank in LAYER_RANKS:
            present = [layer for layer in rank if layer in by_layer]
            if len(present) >= 2:
                lines.append(
                    '  {rank=same; ' + '; '.join(_quote(n) for n in present) + ';}'
                )
    else:
        for rank in LAYER_RANKS:
            for layer in rank:
                if layer not in by_layer:
                    continue
                # cluster fill is the layer colour at ~33% alpha so nodes stand
                # out against the cluster background.
                lines.append(f'  subgraph cluster_{layer} {{')
                lines.append(f'    label="{layer}";')
                lines.append(
                    f'    style="rounded,filled"; fillcolor="{node_colour(layer)}55";'
                )
                lines.append('    fontname="Helvetica"; fontsize=11;')
                # Arrange nodes in a grid of CLUSTER_COLUMNS columns: emit each
                # row as `{rank=same; …}` and chain consecutive rows with one
                # invisible edge. Without this, layers like ``services`` (14
                # nodes) and ``utils`` (13) sprawl horizontally and balloon the
                # diagram to thousands of pt wide.
                nodes_in_layer = by_layer[layer]
                rows = [
                    nodes_in_layer[i : i + CLUSTER_COLUMNS]
                    for i in range(0, len(nodes_in_layer), CLUSTER_COLUMNS)
                ]
                for n in nodes_in_layer:
                    sub_label = n.split(".", 1)[1] if "." in n else n
                    lines.append(
                        f'    "{n}" [label="{sub_label}", fillcolor="{node_colour(layer)}"];'
                    )
                for row in rows:
                    if len(row) >= 2:
                        lines.append(
                            '    {rank=same; '
                            + '; '.join(_quote(n) for n in row)
                            + ';}'
                        )
                for upper, lower in zip(rows, rows[1:]):
                    lines.append(
                        f'    "{upper[0]}" -> "{lower[0]}" [style=invis, weight=10];'
                    )
                lines.append('  }')
                lines.append('')
        # Same-rank constraints across sidecars: use one representative node
        # from each layer in the rank. newrank=true makes this work across
        # cluster boundaries.
        for rank in LAYER_RANKS:
            present_layers = [layer for layer in rank if layer in by_layer]
            if len(present_layers) >= 2:
                reps = [by_layer[layer][0] for layer in present_layers]
                lines.append('  {rank=same; ' + '; '.join(_quote(r) for r in reps) + ';}')

    # Invisible ordering edges along the spine so layers stack in the requested
    # order regardless of how dot would have ordered them from the real edges.
    spine_present = [layer for layer in SPINE if layer in by_layer]
    for a, b in zip(spine_present, spine_present[1:]):
        if level == 1:
            lines.append(f'  "{a}" -> "{b}" [style=invis, weight=100];')
        else:
            rep_a, rep_b = by_layer[a][0], by_layer[b][0]
            lines.append(f'  "{rep_a}" -> "{rep_b}" [style=invis, weight=100];')

    lines.append('')
    for s, d in edges:
        attrs: list[str] = []
        if (s, d) in cycle_edges:
            attrs.append(f'color="{CYCLE_EDGE_COLOUR}"')
            attrs.append('penwidth=2')
        attr_str = f' [{", ".join(attrs)}]' if attrs else ''
        lines.append(f'  "{s}" -> "{d}"{attr_str};')
    lines.append('}')
    return "\n".join(lines) + "\n"


def render_svgs(
    out_dir: Path,
    edges_by_level: dict[str, list[list[str]]],
    excluded: frozenset[str],
) -> bool:
    """Write .dot + .svg for every level. Returns False if ``dot`` is missing."""
    dot_bin = shutil.which("dot")
    if not dot_bin:
        return False
    for level in GRAPH_LEVELS:
        raw = edges_by_level[f"level_{level}"]
        filtered = filter_edges_for_display(raw, level=level, excluded=excluded)
        cycle_edges = detect_cycle_edges(filtered)
        dot_src = render_dot_layered(level, filtered, cycle_edges)
        dot_file = out_dir / f"dependencies_level_{level}.dot"
        svg_file = out_dir / f"dependencies_level_{level}.svg"
        dot_file.write_text(dot_src)
        subprocess.run(
            [dot_bin, "-Tsvg", str(dot_file), "-o", str(svg_file)],
            check=True,
        )
    return True


# ---------- CLI ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if graph.json's edges differ from a fresh build.",
    )
    mode.add_argument(
        "--json-only",
        action="store_true",
        help="Write graph.json but skip .dot/.svg rendering.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="LAYER",
        help=(
            "Drop a top-level layer (e.g. 'automation') from the rendered SVGs. "
            "Repeatable. Affects rendering only; graph.json keeps every edge so "
            "the CI freshness gate is unaffected."
        ),
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    out_dir = root / DIAGRAMS_DIR
    graph_path = out_dir / GRAPH_FILE

    if args.check:
        if not graph_path.exists():
            print(f"{graph_path.relative_to(root)} missing; run scripts/generate_dependency_diagrams.py", file=sys.stderr)
            return 1
        current = json.loads(graph_path.read_text())
        fresh = build_payload(root)
        if current.get("edges") != fresh["edges"]:
            print(
                f"{graph_path.relative_to(root)} is stale; run scripts/generate_dependency_diagrams.py",
                file=sys.stderr,
            )
            return 1
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(root)
    graph_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    edge_total = sum(len(v) for v in payload["edges"].values())
    print(f"Wrote {graph_path.relative_to(root)} ({edge_total} edges across {len(GRAPH_LEVELS)} levels)")

    if args.json_only:
        return 0

    rendered = render_svgs(out_dir, payload["edges"], frozenset(args.exclude))
    if not rendered:
        print(
            "Skipped SVG rendering: 'dot' not found on PATH. "
            "Install Graphviz (`sudo apt install graphviz` on Linux, "
            "`brew install graphviz` on macOS) and rerun without --json-only.",
            file=sys.stderr,
        )
        return 0

    for level in GRAPH_LEVELS:
        rel = (out_dir / f"dependencies_level_{level}.svg").relative_to(root)
        print(f"Rendered {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
