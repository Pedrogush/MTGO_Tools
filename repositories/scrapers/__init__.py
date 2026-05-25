"""Web-scraping clients for external data sources (MTGGoldfish, etc.).

These scrapers are the *source side* of :mod:`repositories.metagame_repository`
and :mod:`repositories.deck_text_cache`: they fetch raw HTML/JSON from external
sites and turn it into the structured records the metagame and deck repos
expose to higher layers. They live under ``repositories/`` (not ``services/``)
because, by the layer rules in ``ARCHITECTURE.md``, the thing that turns "a
remote source of bytes" into "domain-shaped records" is a repository.

Members are exposed only via dotted submodule imports
(``from repositories.scrapers.mtggoldfish import ...``); the package itself
intentionally re-exports nothing, so importing ``repositories.scrapers`` does
not eagerly pull in scraping dependencies.
"""
