"""Deck version-history tab strings. (English (United States))"""

MESSAGES: dict[str, str] = {
    "tabs.deck_history": "History",
    "tabs.tooltip.deck_history": "Every saved version of this deck, the branches between them, and what changed",
    "history.no_branch": "No version history yet",
    "history.empty": "No version history yet — save the deck to create one.",
    "history.on_branch": "On branch {branch}",
    "history.branch.label": "Branch",
    "history.branch.tooltip": "Switch to another branch — this rewrites the deck file on disk",
    "history.branch.title": "Create Branch",
    "history.branch.prompt": "Name the new branch",
    "history.tab.decklist": "Decklist",
    "history.tab.diff": "Diff",
    "history.diff.no_baseline": "This is the first version — there is nothing to compare it against.",
    "history.diff.identical": "No card differences.",
    "history.baseline.none": "Comparing against: parent version",
    "history.baseline.parent": "Comparing against parent {sha}",
    "history.baseline.explicit": "Comparing against pinned baseline {sha}",
    "history.menu.checkout": "Check out this version…",
    "history.menu.branch_here": "Create branch here…",
    "history.menu.set_baseline": "Set as diff baseline",
    "history.checkout.title": "Check Out Version",
    # Says plainly that the file on disk changes: this is the only action in the
    # tab that touches the deck the user keeps.
    "history.checkout.confirm": "Check out version {sha}?\n\nThis rewrites the deck file on disk with that version's decklist.",
    "history.external.title": "Deck Edited Outside the App",
    "history.external.prompt": "This decklist is not a version in the deck's history — it looks like the file was edited outside the app.\n\nRecord it as a new version?",
    "app.status.deck_history_baseline": "Diff baseline set to {sha}",
    "app.status.deck_history_branched": "Created branch {branch}",
    "app.status.deck_history_checked_out": "Checked out {sha} on branch {branch}",
    "app.status.deck_history_switched": "Switched to branch {branch}",
    "app.status.deck_version_saved": "Version saved: {summary}",
}
