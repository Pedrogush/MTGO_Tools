"""Mana-query parsing helpers that do not depend on wx."""

from __future__ import annotations


def normalize_mana_query(raw: str) -> str:
    """Normalize free-form mana input into ``{}``-wrapped tokens."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "{" in text and "}" in text:
        return text
    upper_text = text.upper()
    tokens: list[str] = []
    i = 0
    length = len(upper_text)
    while i < length:
        ch = upper_text[i]
        if ch.isspace() or ch in {",", ";"}:
            i += 1
            continue
        if ch.isdigit():
            num = ch
            i += 1
            while i < length and upper_text[i].isdigit():
                num += upper_text[i]
                i += 1
            tokens.append(num)
            continue
        if ch == "{":
            end = upper_text.find("}", i + 1)
            if end != -1:
                tokens.append(upper_text[i + 1 : end])
                i = end + 1
                continue
            i += 1
            continue
        if ch in {"/", "}"}:
            i += 1
            continue
        if ch.isalpha() or ch in {"∞", "½"}:
            token = ch
            i += 1
            while i < length and (upper_text[i].isalpha() or upper_text[i] in {"/", "½"}):
                token += upper_text[i]
                i += 1
            if "/" in token:
                tokens.append(token)
            elif len(token) > 1:
                tokens.extend(token)
            else:
                tokens.append(token)
            continue
        i += 1
    return "".join(f"{{{tok}}}" for tok in tokens if tok)


def tokenize_mana_symbols(cost: str) -> list[str]:
    """Split a mana-cost string into uppercase symbol tokens."""
    tokens: list[str] = []
    if not cost:
        return tokens
    for part in cost.replace("}", "").split("{"):
        token = part.strip()
        if token:
            tokens.append(token.upper())
    return tokens
