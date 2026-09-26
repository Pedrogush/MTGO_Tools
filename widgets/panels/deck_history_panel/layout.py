"""Turning a deck's commits into rows and lanes for the graph view.

wxPython has no commit-graph widget and no DAG layout library to borrow one
from, so the lanes are assigned here and painted by
:mod:`widgets.panels.deck_history_panel.graph_canvas`. Keeping the assignment in
a module that imports no wx is what lets the fork case be tested directly,
rather than inferred from a screenshot.

The problem is a good deal smaller than a general commit graph: deck history
never merges (the feature ships without merging on purpose), so every commit has
at most one parent and the history is a *tree* of chains growing out of shared
ancestors. That removes the hard part of git's own layout -- edges that rejoin --
and leaves two rules: a child is always drawn above its parent, and a chain keeps
its lane until something else has already claimed the lane its parent sits in.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.deck_vcs_service import CardDelta, DeckDiff, GraphCommit


@dataclass(frozen=True)
class GraphNode:
    """One commit, placed."""

    graph_commit: GraphCommit
    row: int
    lane: int

    @property
    def sha(self) -> str:
        return self.graph_commit.sha


@dataclass(frozen=True)
class GraphEdge:
    """A link from a commit down to its parent."""

    child_sha: str
    parent_sha: str
    child_row: int
    child_lane: int
    parent_row: int
    parent_lane: int

    @property
    def is_fork(self) -> bool:
        """True when the edge changes lane, i.e. this is where a branch diverged."""
        return self.child_lane != self.parent_lane


@dataclass(frozen=True)
class GraphLayout:
    """Placed commits plus the edges between them."""

    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    lane_count: int = 0

    def node_for(self, sha: str) -> GraphNode | None:
        return next((node for node in self.nodes if node.sha == sha), None)


def _topological_rows(commits: list[GraphCommit]) -> list[GraphCommit]:
    """``commits`` newest first, with every child strictly above its parent.

    Commit timestamps have one-second resolution, so several saves made in the
    same second sort arbitrarily by time alone -- which would let a parent be
    drawn above its child. Ordering by ancestry first and time only as a
    tiebreak keeps the picture correct however fast the user clicked save.
    """
    by_sha = {commit.sha: commit for commit in commits}
    # Children that are actually present; a parent outside the set (shouldn't
    # happen, but a truncated walk would do it) must not block its child.
    pending_children: dict[str, int] = dict.fromkeys(by_sha, 0)
    for commit in commits:
        for parent in commit.commit.parents:
            if parent in pending_children:
                pending_children[parent] += 1

    ready = [sha for sha, count in pending_children.items() if count == 0]
    ordered: list[GraphCommit] = []
    while ready:
        # Newest first among everything currently drawable.
        ready.sort(key=lambda sha: (-by_sha[sha].commit.timestamp, sha))
        sha = ready.pop(0)
        commit = by_sha[sha]
        ordered.append(commit)
        for parent in commit.commit.parents:
            if parent in pending_children:
                pending_children[parent] -= 1
                if pending_children[parent] == 0:
                    ready.append(parent)

    # A cycle is impossible in a commit DAG, but never silently drop commits.
    if len(ordered) < len(commits):
        placed = {commit.sha for commit in ordered}
        ordered.extend(commit for commit in commits if commit.sha not in placed)
    return ordered


def build_layout(commits: list[GraphCommit]) -> GraphLayout:
    """Place ``commits`` into rows and lanes for painting."""
    if not commits:
        return GraphLayout()

    ordered = _topological_rows(commits)

    # lane -> the sha that lane is currently waiting to reach. A lane is claimed
    # by a chain and released when that chain ends or joins another lane.
    waiting: dict[int, str] = {}
    lane_of: dict[str, int] = {}
    rows: dict[str, int] = {}

    for row, commit in enumerate(ordered):
        sha = commit.sha
        lane = next((index for index, expected in sorted(waiting.items()) if expected == sha), None)
        if lane is None:
            lane = next(index for index in range(len(waiting) + 1) if index not in waiting)
        lane_of[sha] = lane
        rows[sha] = row

        parent = commit.commit.parents[0] if commit.commit.parents else None
        if parent is None:
            waiting.pop(lane, None)
            continue
        already = next(
            (index for index, expected in waiting.items() if expected == parent and index != lane),
            None,
        )
        if already is not None:
            # An earlier (newer) child of this parent already owns the lane the
            # parent will sit in, so this chain stops here and its edge routes
            # across -- that bend is the fork the user is looking for.
            waiting.pop(lane, None)
        else:
            waiting[lane] = parent

    nodes = tuple(
        GraphNode(graph_commit=commit, row=rows[commit.sha], lane=lane_of[commit.sha])
        for commit in ordered
    )

    edges: list[GraphEdge] = []
    for commit in ordered:
        for parent in commit.commit.parents:
            if parent not in rows:
                continue
            edges.append(
                GraphEdge(
                    child_sha=commit.sha,
                    parent_sha=parent,
                    child_row=rows[commit.sha],
                    child_lane=lane_of[commit.sha],
                    parent_row=rows[parent],
                    parent_lane=lane_of[parent],
                )
            )

    return GraphLayout(
        nodes=nodes,
        edges=tuple(edges),
        lane_count=max(lane_of.values()) + 1,
    )


def _amount(value: float) -> str:
    """A card count as a player writes it: ``2``, never ``2.0``."""
    return str(int(value) if float(value).is_integer() else value)


def _delta_line(delta: CardDelta) -> str:
    """One card's net change, signed: ``-2 Pinnacle Emissary``."""
    sign = "+" if delta.delta > 0 else "-"
    return f"{sign}{_amount(abs(delta.delta))} {delta.name}"


def diff_lines(
    diff: DeckDiff,
    *,
    before_label: str,
    after_label: str,
    main_heading: str,
    sideboard_heading: str,
    identical: str,
) -> list[str]:
    """A deck diff as **net card changes**, grouped by zone.

    A unified text diff is correct and unreadable: cutting a playset to two
    shows up as a removed line and an added line, which is git's answer to
    "what changed in this file" rather than a player's answer to "what changed
    in this deck". The card-level diff already computes the net, so ``4 -> 2``
    is one ``-2`` line.

    The zones are kept apart because the diff keys on ``(name, is_sideboard)``:
    moving two copies to the sideboard is ``-2`` in one zone and ``+2`` in the
    other, and collapsing by card name alone would cancel a real change into
    nothing.
    """
    header = [f"{before_label} -> {after_label}"]
    if diff.is_empty:
        return [*header, "", identical]

    by_zone: dict[bool, list[CardDelta]] = {False: [], True: []}
    for delta in (*diff.added, *diff.changed, *diff.removed):
        by_zone[delta.is_sideboard].append(delta)

    lines = list(header)
    for is_sideboard, heading in ((False, main_heading), (True, sideboard_heading)):
        zone = by_zone[is_sideboard]
        if not zone:
            continue
        zone.sort(key=lambda d: (-d.delta, d.name.casefold()))
        lines.extend(("", heading))
        lines.extend(_delta_line(delta) for delta in zone)
    return lines
