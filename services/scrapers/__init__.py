"""Web-scraping clients for external data sources (MTGGoldfish, etc.).

Members are exposed only via dotted submodule imports
(``from services.scrapers.mtggoldfish import ...``); the package itself
intentionally re-exports nothing, so importing ``services.scrapers`` does not
eagerly pull in scraping dependencies.
"""
