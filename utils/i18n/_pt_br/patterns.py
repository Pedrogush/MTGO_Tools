"""Deck patterns (capability explorer) tab strings. (Português (Brasil))"""

MESSAGES: dict[str, str] = {
    "tabs.deck_patterns": "Padrões",
    "tabs.tooltip.deck_patterns": "O que este deck poderia conjurar em cada turno, com cada combinação de terrenos possível",
    "patterns.ceiling": (
        "Teto de capacidade — assume que todo o decklist está na mão e que nenhum "
        "terreno, mana ou estado de jogo passa de um turno para outro. Não é uma probabilidade."
    ),
    "patterns.turn": "Turno",
    "patterns.turn.tooltip": "Turno N significa N terrenos em jogo — cada turno é avaliado isoladamente",
    "patterns.refresh": "Recalcular",
    "patterns.combination": "{lands} — {mana} de mana",
    "patterns.no_plays": "Nada conjurável com esta mana",
    "patterns.status.computing": "Calculando…",
    "patterns.status.no_deck": "Carregue um deck para ver o que ele pode fazer.",
    "patterns.status.no_lands": "Nenhum terreno que produz mana no deck principal.",
    "patterns.status.summary": "Turno {turn}: {combinations} combinações de terrenos, {playable} com jogada",
    "patterns.status.truncated": "truncado, exibindo resultados parciais",
    "patterns.status.failed": "Não foi possível calcular os padrões deste deck.",
}
