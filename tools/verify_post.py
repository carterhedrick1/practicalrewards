#!/usr/bin/env python3
"""Run deterministic and independent-model accuracy checks on today's post."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import (
    ROOT, STATE, TOOLS, canonical_card_source_url, card_mentions,
    compact_card, fetch_article_text, fill_template, html_to_text,
    parse_json_reply, read_json, recompute_calculation, run_codex,
    validate_calculations, validate_public_http_url, write_json,
)


SIGNED_MONEY_PATTERN = (
    r"(?:(?<![^\s(])-\$|\u2212\$|\$[-\u2212]?)\s*"
    r"\d[\d,]*(?:\.\d+)?"
)
MONEY_OR_MULTIPLIER_RE = re.compile(
    rf"{SIGNED_MONEY_PATTERN}\+?|\b\d+(?:\.\d+)?x\b",
    re.IGNORECASE,
)
RANGE_SEPARATOR_RE = r"(?:[-–—]|\bto\b)"
REWARDS_UNIT_RE = r"(?:points?|pts?|miles?|mi)"
CPP_UNIT_RE = (
    r"(?:¢(?:\s*/\s*(?:pt|point|mi|mile)|\s+per\s+(?:point|mile))?|"
    r"cpp|cpm|cents?\s+per\s+(?:point|mile))"
)
KEY_NUMBER_RE = re.compile(
    rf"{SIGNED_MONEY_PATTERN}\+?|"
    r"\b\d+(?:\.\d+)?(?:x\b|%(?![a-z0-9])|[\s-]+percent(?:age)?s?\b)|"
    r"\b\d[\d,]*(?:\.\d+)?[kK]?(?:[\s®™℠-]+[A-Za-z]+){0,3}"
    rf"[\s®™℠-]+{REWARDS_UNIT_RE}\b|"
    r"\b\d[\d,]*(?:\.\d+)?[\s-]*"
    r"(?:credits?|days?|hours?|months?|nights?|weeks?|years?)\b",
    re.IGNORECASE,
)
MONEY_RANGE_RE = re.compile(
    rf"\$\s*(\d[\d,]*(?:\.\d+)?)\s*{RANGE_SEPARATOR_RE}\s*\$?\s*(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
MULTIPLIER_RANGE_RE = re.compile(
    rf"\b(\d+(?:\.\d+)?)\s*x?\s*{RANGE_SEPARATOR_RE}\s*(\d+(?:\.\d+)?)\s*(x)\b",
    re.IGNORECASE,
)
PERCENT_RANGE_RE = re.compile(
    rf"\b(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?s?)?\s*{RANGE_SEPARATOR_RE}\s*"
    rf"(\d+(?:\.\d+)?)\s*(%|percent(?:age)?s?)(?![a-z0-9])",
    re.IGNORECASE,
)
POINTS_RANGE_RE = re.compile(
    rf"\b(\d[\d,]*(?:\.\d+)?[kK]?)\s*({REWARDS_UNIT_RE})?\s*{RANGE_SEPARATOR_RE}\s*"
    rf"(\d[\d,]*(?:\.\d+)?[kK]?)\s*({REWARDS_UNIT_RE})\b",
    re.IGNORECASE,
)
QUANTITY_RANGE_RE = re.compile(
    rf"\b(\d[\d,]*(?:\.\d+)?)\s*"
    rf"(?:(credits?|days?|hours?|months?|nights?|weeks?|years?))?\s*"
    rf"{RANGE_SEPARATOR_RE}\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(credits?|days?|hours?|months?|nights?|weeks?|years?)\b",
    re.IGNORECASE,
)
CPP_RANGE_RE = re.compile(
    rf"\b(\d+(?:\.\d+)?)\s*(?:{CPP_UNIT_RE})?\s*{RANGE_SEPARATOR_RE}\s*"
    rf"(\d+(?:\.\d+)?)\s*({CPP_UNIT_RE})(?![a-z0-9])",
    re.IGNORECASE,
)
CPP_RE = re.compile(
    rf"\b\d+(?:\.\d+)?\s*{CPP_UNIT_RE}(?![a-z0-9])",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(?:20\d{2}|\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)\b|"
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)
DEADLINE_YEAR_RE = re.compile(
    r"\b(?:by|before|through|until|ends?|expires?|deadline|effective)\b"
    r"[^.!?;]{0,50}?\b(20\d{2})\b",
    re.IGNORECASE,
)
PLAIN_TEXT_MARKUP_RE = re.compile(
    r"<[^>]*>|&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);",
    re.IGNORECASE,
)


def normalize_number(value: str) -> str:
    compact = re.sub(r"[\s,]", "", value).casefold().replace("\u2212", "-").rstrip("+")
    negative = False
    if compact.startswith("-$"):
        negative = True
        compact = "$" + compact[2:]
    elif compact.startswith("$-"):
        negative = True
        compact = "$" + compact[2:]
    elif compact.startswith("-"):
        negative = True
        compact = compact[1:]
    # Preserve the previous treatment of hyphens inside unit-bearing forms.
    compact = compact.replace("-", "")
    cpp = re.fullmatch(
        r"(\d+(?:\.\d+)?)(?:cpp|cpm|"
        r"¢(?:/(?:pt|point|mi|mile)|per(?:point|mile))?|"
        r"cents?per(?:point|mile))",
        compact,
    )
    if cpp:
        amount = float(cpp.group(1))
        return (str(int(amount)) if amount.is_integer() else f"{amount:g}") + "cpp"
    quantity = re.fullmatch(
        r"(\d+(?:\.\d+)?)(k)?[a-z®™℠]*"
        r"(points?|pts?|miles?|mi|credits?|days?|hours?|months?|nights?|weeks?|years?)",
        compact,
    )
    if quantity:
        amount = float(quantity.group(1)) * (1000 if quantity.group(2) else 1)
        number = str(int(amount)) if amount.is_integer() else f"{amount:g}"
        unit = quantity.group(3)
        if re.fullmatch(r"points?|pts?|miles?|mi", unit):
            return number + "point"
        if unit.endswith("s"):
            unit = unit[:-1]
        return number + unit
    simple = re.fullmatch(r"(\$?)(\d+(?:\.\d+)?)(%|x|percent(?:age)?s?)?", compact)
    if simple:
        amount = float(simple.group(2))
        number = str(int(amount)) if amount.is_integer() else f"{amount:g}"
        suffix = simple.group(3) or ""
        if suffix.startswith("percent"):
            suffix = "%"
        sign = "-" if negative else ""
        return simple.group(1) + sign + number + suffix
    return compact


def normalize_date(value: str) -> str:
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned.replace(",", " ")).strip()
    formats = (
        "%B %Y", "%b %Y",
        "%B %d %Y", "%b %d %Y", "%B %d", "%b %d",
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m/%d",
    )
    for date_format in formats:
        try:
            parsed = dt.datetime.strptime(cleaned, date_format)
            if date_format in {"%B %Y", "%b %Y"}:
                return parsed.strftime("date:%Y-%m")
            if "%Y" in date_format or "%y" in date_format:
                return parsed.strftime("date:%Y-%m-%d")
            return parsed.strftime("date:--%m-%d")
        except ValueError:
            continue
    return "date:" + re.sub(r"\s+", "", cleaned.casefold())


def iter_numeric_claims(value: str, key_numbers: bool = False) -> list[tuple[int, int, str, str]]:
    """Return (start, end, raw, normalized) numeric claims without overlaps."""
    matches: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    range_patterns: list[tuple[re.Pattern[str], str]] = [
        (MONEY_RANGE_RE, "money"),
        (MULTIPLIER_RANGE_RE, "unit"),
    ]
    if key_numbers:
        range_patterns.extend((
            (CPP_RANGE_RE, "cpp"),
            (PERCENT_RANGE_RE, "unit"),
            (POINTS_RANGE_RE, "points"),
            (QUANTITY_RANGE_RE, "quantity"),
        ))
    for pattern, kind in range_patterns:
        for match in pattern.finditer(value):
            if any(match.start() < used_end and match.end() > used_start for used_start, used_end in occupied):
                continue
            if kind == "money":
                raw_values = ("$" + match.group(1), "$" + match.group(2))
            elif kind == "cpp":
                raw_values = (match.group(1) + match.group(3), match.group(2) + match.group(3))
            elif kind in {"points", "quantity"}:
                first_unit = match.group(2) or match.group(4)
                raw_values = (
                    match.group(1) + " " + first_unit,
                    match.group(3) + " " + match.group(4),
                )
            else:
                raw_values = (match.group(1) + " " + match.group(3), match.group(2) + " " + match.group(3))
            endpoint_groups = (1, 3) if kind in {"points", "quantity"} else (1, 2)
            for group_index, raw in zip(endpoint_groups, raw_values):
                start, end = match.span(group_index)
                matches.append((start, end, raw, normalize_number(raw)))
            occupied.append(match.span())

    patterns = [DATE_RE, CPP_RE, KEY_NUMBER_RE] if key_numbers else [MONEY_OR_MULTIPLIER_RE]
    for pattern in patterns:
        for match in pattern.finditer(value):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            raw = match.group(0)
            token = normalize_date(raw) if pattern is DATE_RE else normalize_number(raw)
            matches.append((start, end, raw, token))
            occupied.append((start, end))
    if key_numbers:
        for match in DEADLINE_YEAR_RE.finditer(value):
            start, end = match.span(1)
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            raw = match.group(1)
            matches.append((start, end, raw, "date-year:" + raw))
            occupied.append((start, end))
    return sorted(matches, key=lambda item: (item[0], item[1]))


def numeric_tokens(value: str, key_numbers: bool = False) -> set[str]:
    tokens = {claim[3] for claim in iter_numeric_claims(value, key_numbers=key_numbers)}
    if key_numbers:
        for token in list(tokens):
            full_date = re.fullmatch(r"date:(\d{4})-(\d{2})-(\d{2})", token)
            if full_date:
                tokens.add(f"date:--{full_date.group(2)}-{full_date.group(3)}")
                tokens.add("date-year:" + full_date.group(1))
            month_year = re.fullmatch(r"date:(\d{4})-(\d{2})", token)
            if month_year:
                tokens.add("date-year:" + month_year.group(1))
    return tokens


class ContentBlockParser(HTMLParser):
    """Collect text blocks, math rows, and table rows with boundaries intact."""

    TEXT_BLOCKS = {"h2", "h3", "p", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, list[str]]] = []
        self._block_tag: str | None = None
        self._block_kind: str | None = None
        self._block_depth = 0
        self._block_parts: list[str] = []
        self._row_cells: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        class_names = set((dict(attrs).get("class") or "").split())
        if self._block_tag is not None:
            self._block_depth += 1
            return
        if lower == "tr":
            self._row_cells = []
            self._cell_parts = None
        elif lower in {"td", "th"} and self._row_cells is not None:
            self._cell_parts = []
        elif (
            "pr-math-row" in class_names
            and self._row_cells is None
        ):
            self._block_tag = lower
            self._block_kind = (
                "pr-math-total" if "pr-math-total" in class_names else "pr-math-row"
            )
            self._block_depth = 1
            self._block_parts = []
        elif lower in self.TEXT_BLOCKS and self._row_cells is None:
            self._block_tag = lower
            self._block_kind = lower
            self._block_depth = 1
            self._block_parts = []

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if self._block_tag is not None:
            self._block_depth -= 1
            if self._block_depth:
                return
            text = re.sub(r"\s+", " ", "".join(self._block_parts)).strip()
            if text:
                self.blocks.append((self._block_kind or self._block_tag, [text]))
            self._block_tag = None
            self._block_kind = None
            self._block_parts = []
        elif lower in {"td", "th"} and self._row_cells is not None and self._cell_parts is not None:
            self._row_cells.append(re.sub(r"\s+", " ", "".join(self._cell_parts)).strip())
            self._cell_parts = None
        elif lower == "tr" and self._row_cells is not None:
            if any(self._row_cells):
                self.blocks.append(("tr", self._row_cells))
            self._row_cells = None
            self._cell_parts = None

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)
        elif self._block_tag is not None:
            self._block_parts.append(data)


def content_blocks(content_html: str) -> list[list[str]]:
    parser = ContentBlockParser()
    parser.feed(content_html or "")
    parser.close()
    return [cells for _tag, cells in parser.blocks]


def structured_content_blocks(content_html: str) -> list[tuple[str, list[str]]]:
    parser = ContentBlockParser()
    parser.feed(content_html or "")
    parser.close()
    return parser.blocks


def math_subtraction_operand_tokens(content_html: str) -> set[str]:
    """Return signed money tokens used exclusively as non-total math line items."""
    operands: set[str] = set()
    non_operands: set[str] = set()
    for kind, cells in structured_content_blocks(content_html):
        signed_money = {
            token
            for cell in cells
            for token in numeric_tokens(cell, key_numbers=True)
            if re.fullmatch(r"\$-\d+(?:\.\d+)?", token)
        }
        if kind == "pr-math-row":
            operands.update(signed_money)
        else:
            non_operands.update(signed_money)
    return operands - non_operands


def signed_math_total_tokens(content_html: str) -> set[str]:
    """Return signed money tokens displayed as worked-math totals."""
    return {
        token
        for kind, cells in structured_content_blocks(content_html)
        if kind == "pr-math-total"
        for cell in cells
        for token in numeric_tokens(cell, key_numbers=True)
        if re.fullmatch(r"\$-\d+(?:\.\d+)?", token)
    }


def signed_math_operand_is_supported(
    token: str,
    math_operands: set[str],
    supported_numbers: set[str],
) -> bool:
    """Allow −$300 as display syntax only when positive $300 is supported."""
    match = re.fullmatch(r"\$-(\d+(?:\.\d+)?)", token)
    return bool(
        match
        and token in math_operands
        and f"${match.group(1)}" in supported_numbers
    )


def _span_distance(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
    if first_end <= second_start:
        return second_start - first_end
    if second_end <= first_start:
        return first_start - second_end
    return 0


def _clause_bounds(value: str, start: int, end: int) -> tuple[int, int]:
    boundaries = ".!?;\n"
    before = max((value.rfind(marker, 0, start) for marker in boundaries), default=-1)
    after_positions = [value.find(marker, end) for marker in boundaries]
    after_positions = [position for position in after_positions if position >= 0]
    return before + 1, min(after_positions, default=len(value))


def associated_numeric_claims(
    content_html: str,
    cards: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str, str, str]]:
    """Associate each key numeric claim with matched card context."""
    associated, _unassociated, _illustrative, _named_claims = scan_card_numeric_claims(content_html, cards)
    return associated


def scan_card_numeric_claims(
    content_html: str,
    cards: list[dict[str, Any]],
) -> tuple[
    list[tuple[dict[str, Any], str, str, str]],
    list[tuple[str, str]],
    list[str],
    bool,
]:
    associated: list[tuple[dict[str, Any], str, str, str]] = []
    unassociated: list[tuple[str, str]] = []
    illustrative_sentences: list[str] = []
    named_claims_present = False
    heading_context: list[dict[str, Any]] = []
    for tag, cells in structured_content_blocks(content_html):
        mentions_by_cell = [card_mentions(cell, cards) for cell in cells]
        heading_cards = list({mention[2].get("id"): mention[2] for mentions in mentions_by_cell for mention in mentions}.values())
        if tag == "h2":
            heading_context = heading_cards
        elif tag == "h3" and heading_cards:
            heading_context = heading_cards
        for cell_index, cell in enumerate(cells):
            for start, end, raw, token in iter_numeric_claims(cell, key_numbers=True):
                clause_start, clause_end = _clause_bounds(cell, start, end)
                clause = cell[clause_start:clause_end].strip()
                same_clause = [
                    mention for mention in mentions_by_cell[cell_index]
                    if mention[0] >= clause_start and mention[1] <= clause_end
                ]
                candidates = same_clause or mentions_by_cell[cell_index]
                if candidates:
                    named_claims_present = True
                    mention = min(
                        candidates,
                        key=lambda item: _span_distance(start, end, item[0], item[1]),
                    )
                else:
                    row_candidates = [
                        (other_index, mention)
                        for other_index, mentions in enumerate(mentions_by_cell)
                        for mention in mentions
                    ]
                    if row_candidates:
                        named_claims_present = True
                        _, mention = min(
                            row_candidates,
                            key=lambda item: (
                                abs(item[0] - cell_index),
                                0 if item[0] < cell_index else 1,
                                abs(item[1][0] - start),
                            ),
                        )
                    elif heading_context:
                        named_claims_present = True
                        associated.extend(
                            (heading_card, raw, token, cell)
                            for heading_card in heading_context
                        )
                        continue
                    else:
                        illustrative_sentences.append(clause)
                        continue
                associated.append((mention[2], raw, token, cell))
    return associated, unassociated, list(dict.fromkeys(illustrative_sentences)), named_claims_present


def _numeric_counter(value: str) -> Counter[str]:
    return Counter(token for _start, _end, _raw, token in iter_numeric_claims(value, key_numbers=True))


def _calculation_matches_sentence(calculation: dict[str, Any], sentence: str) -> bool:
    sentence_numbers = _numeric_counter(sentence)
    evidence_numbers: Counter[str] = Counter()
    for raw_value in list(calculation.get("inputs", [])) + [calculation.get("result", "")]:
        tokens = _numeric_counter(str(raw_value))
        if not tokens:
            tokens[normalize_number(str(raw_value))] += 1
        evidence_numbers.update(tokens)
    return bool(evidence_numbers) and all(
        sentence_numbers[token] >= count for token, count in evidence_numbers.items()
    )


def illustrative_claim_findings(
    sentences: list[str],
    calculations: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    packet: list[dict[str, Any]] = []
    calculation_list = calculations if isinstance(calculations, list) else []
    for sentence in sentences:
        matching = [
            calculation for calculation in calculation_list
            if isinstance(calculation, dict) and _calculation_matches_sentence(calculation, sentence)
        ]
        evidence_status = "not_required"
        evidence_error: str | None = None
        if matching:
            try:
                validate_calculations(matching)
                evidence_status = "verified"
            except ValueError as error:
                evidence_status = "invalid"
                evidence_error = str(error)
        elif sum(_numeric_counter(sentence).values()) >= 3:
            evidence_status = "missing"
        warnings.append(f"illustrative generic card-number example: {sentence}")
        if evidence_status == "missing":
            warnings.append(f"illustrative arithmetic has no matching calculation evidence: {sentence}")
        packet.append({
            "sentence": sentence,
            "numeric_claims": [raw for _start, _end, raw, _token in iter_numeric_claims(sentence, key_numbers=True)],
            "calculation_evidence": evidence_status,
            **({"calculation_error": evidence_error} if evidence_error else {}),
        })
    return list(dict.fromkeys(warnings)), packet


def check_card_number_findings(
    content_html: str,
    cards: list[dict[str, Any]],
    source_texts: list[str] | None = None,
    calculations: Any = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    sourced = set().union(*(numeric_tokens(text, key_numbers=True) for text in (source_texts or [])))
    known_by_id: dict[Any, set[str]] = {}
    for card in cards:
        known_text = json.dumps(compact_card(card), ensure_ascii=False)
        known = numeric_tokens(known_text, key_numbers=True)
        annual_fee = card.get("annual_fee")
        if isinstance(annual_fee, (int, float)) and not isinstance(annual_fee, bool):
            known.add(normalize_number(f"${annual_fee:g}"))
        known_by_id[card.get("id")] = known
    all_known = set().union(*known_by_id.values())
    calculated, _calculation_failures = calculation_evidence(
        calculations if calculations is not None else [], all_known, sourced,
    )
    math_operands = math_subtraction_operand_tokens(content_html)
    math_totals = signed_math_total_tokens(content_html)
    associated, _unassociated, illustrative, named_claims_present = scan_card_numeric_claims(content_html, cards)
    for card, raw, token, _block in associated:
        supported_for_card = known_by_id.get(card.get("id"), set()) | sourced | calculated
        if token in math_totals:
            token_is_supported = token in calculated
        else:
            token_is_supported = (
                token in supported_for_card
                or signed_math_operand_is_supported(token, math_operands, supported_for_card)
            )
        if token_is_supported:
            continue
        failures.append(
            f"{card.get('name', '')}: {raw.strip()} is associated with this card but does not match cards.json or fetched source text"
        )
    if named_claims_present and not associated:
        failures.append("card-related numeric claims were present but none could be associated with a card")
    illustrative_warnings, illustrative_packet = illustrative_claim_findings(
        illustrative, calculations if calculations is not None else [],
    )
    return list(dict.fromkeys(failures)), illustrative_warnings, illustrative_packet


def check_card_numbers(
    content_html: str,
    cards: list[dict[str, Any]],
    source_texts: list[str] | None = None,
    calculations: Any = None,
) -> list[str]:
    failures, _warnings, _packet = check_card_number_findings(
        content_html, cards, source_texts, calculations,
    )
    return failures


def words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def eight_grams(value: str) -> set[tuple[str, ...]]:
    tokens = words(value)
    return {tuple(tokens[index:index + 8]) for index in range(max(0, len(tokens) - 7))}


class DocumentCheckParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.problems: list[str] = []
        self.json_ld_parts: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower not in self.VOID:
            self.stack.append(lower)
        if lower == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "script" and self._in_json_ld:
            self._in_json_ld = False
        if lower in self.VOID:
            return
        if not self.stack:
            self.problems.append(f"unexpected closing tag </{tag}>")
            return
        if self.stack[-1] == lower:
            self.stack.pop()
            return
        if lower in self.stack:
            self.problems.append(f"misnested closing tag </{tag}>")
            while self.stack and self.stack[-1] != lower:
                self.stack.pop()
            if self.stack:
                self.stack.pop()
        else:
            self.problems.append(f"closing tag </{tag}> has no opener")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self.json_ld_parts.append(data)

    def finish(self) -> None:
        if self.stack:
            self.problems.append("unclosed tags: " + ", ".join(self.stack[-8:]))


def validate_built_html(slug: str) -> list[str]:
    failures: list[str] = []
    path = ROOT / "blog" / f"{slug}.html"
    if not path.exists():
        return [f"generated post is missing: {path}"]
    value = path.read_text(encoding="utf-8")
    parser = DocumentCheckParser()
    try:
        parser.feed(value)
        parser.close()
        parser.finish()
        failures.extend(f"HTML parse: {problem}" for problem in parser.problems)
    except Exception as error:
        failures.append(f"HTML parser raised {type(error).__name__}: {error}")
    raw_json_ld = "".join(parser.json_ld_parts).strip()
    if not raw_json_ld:
        failures.append("Article JSON-LD block is missing or empty")
    else:
        try:
            parsed = json.loads(raw_json_ld)
            if not isinstance(parsed, dict) or parsed.get("@type") != "Article":
                failures.append("JSON-LD is valid JSON but is not an Article object")
        except json.JSONDecodeError as error:
            failures.append(f"Article JSON-LD is invalid JSON: {error}")
    return failures


def validate_llm_reply(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("verifier response is not an object")
    if not isinstance(value.get("facts_ok"), bool):
        raise ValueError("verifier facts_ok is not boolean")
    score = value.get("voice_score_0_10")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 10:
        raise ValueError("verifier voice score is outside 0-10")
    problems = value.get("problems")
    if not isinstance(problems, list):
        raise ValueError("verifier problems is not a list")
    normalized_problems: list[dict[str, str]] = []
    for problem in problems:
        # Treat legacy unclassified findings conservatively as errors.
        if isinstance(problem, str) and problem.strip():
            normalized_problems.append({"severity": "error", "message": problem.strip()})
            continue
        if not isinstance(problem, dict):
            raise ValueError("each verifier problem must be an object")
        severity = problem.get("severity")
        message = problem.get("message")
        if severity not in {"error", "warning"}:
            raise ValueError("verifier problem severity must be error or warning")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("verifier problem message must be non-empty")
        normalized_problems.append({"severity": severity, "message": message.strip()})
    return {
        "facts_ok": value["facts_ok"],
        "voice_score_0_10": score,
        "problems": normalized_problems,
    }


def llm_review_findings(llm_result: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    if not llm_result["facts_ok"]:
        failures.append("independent verifier marked facts_ok=false")
    if llm_result["voice_score_0_10"] < 6:
        failures.append(
            f"independent verifier voice score {llm_result['voice_score_0_10']} is below 6"
        )
    for problem in llm_result["problems"]:
        rendered = f"verifier problem: {problem['message']}"
        if problem["severity"] == "error":
            failures.append(rendered)
        else:
            warnings.append(rendered)
    return failures, warnings


def first_person_hard_rule_failures(content_html: str) -> list[str]:
    anecdote_text = html_to_text(re.sub(
        r"</(?:h2|h3|p|li|td|th)\s*>",
        ". ",
        content_html,
        flags=re.IGNORECASE,
    ))
    if re.search(r"\b(?:I|me|my|mine|myself)\b", anecdote_text, re.IGNORECASE):
        return ["first-person-singular anecdote violates the no-fabricated-anecdote rule"]
    return []


def independent_check(prompt: str) -> tuple[str, dict[str, Any], str | None]:
    fallback_reason: str | None = None
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku"],
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"claude exited {result.returncode}: {detail[-1000:]}")
        checked = validate_llm_reply(parse_json_reply(result.stdout))
        return "claude-haiku", checked, None
    except Exception as error:
        fallback_reason = f"Claude verifier unavailable or invalid: {error}"
        reply = run_codex(prompt, reasoning_effort="high")
        checked = validate_llm_reply(parse_json_reply(reply))
        return "codex-fallback (reduced independence)", checked, fallback_reason


def card_key_numbers(card: dict[str, Any]) -> set[str]:
    known = numeric_tokens(
        json.dumps(compact_card(card), ensure_ascii=False),
        key_numbers=True,
    )
    annual_fee = card.get("annual_fee")
    if isinstance(annual_fee, (int, float)) and not isinstance(annual_fee, bool):
        known.add(normalize_number(f"${annual_fee:g}"))
    return known


def bare_count_matches_unit_quantity(
    input_tokens: set[str],
    supported_inputs: set[str],
) -> bool:
    """Match a bare count such as 4 to a sourced token such as 4year."""
    bare_counts = {
        token for token in input_tokens
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token)
    }
    if not bare_counts:
        return False
    for supported in supported_inputs:
        quantity = re.fullmatch(
            r"([+-]?\d+(?:\.\d+)?)"
            r"(?:point|credit|day|hour|month|night|week|year)",
            supported,
        )
        if quantity and quantity.group(1) in bare_counts:
            return True
    return False


def calculation_evidence(
    calculations: Any,
    known_numbers: set[str],
    source_numbers: set[str],
    illustrative_sentences: list[str] | None = None,
) -> tuple[set[str], list[str]]:
    accepted_results: set[str] = set()
    failures: list[str] = []
    try:
        validated = validate_calculations(calculations)
    except ValueError as error:
        return set(), [f"invalid calculation evidence: {error}"]
    supported_inputs = known_numbers | source_numbers
    for index, calculation in enumerate(validated):
        recompute_calculation(calculation)
        illustrative_match = any(
            _calculation_matches_sentence(calculation, sentence)
            for sentence in (illustrative_sentences or [])
        )
        for raw_input in calculation["inputs"]:
            tokens = numeric_tokens(str(raw_input), key_numbers=True)
            if not tokens:
                tokens = {normalize_number(str(raw_input))}
            input_is_supported = bool(
                tokens & supported_inputs
                or bare_count_matches_unit_quantity(tokens, supported_inputs)
            )
            if not input_is_supported and not illustrative_match:
                failures.append(
                    f"calculation {index} input {raw_input!r} does not match cards.json, "
                    "fetched source text, or a prior calculation result"
                )
        result_tokens = numeric_tokens(str(calculation["result"]), key_numbers=True)
        if not result_tokens:
            normalized = normalize_number(str(calculation["result"]))
            result_tokens = {normalized, "$" + normalized.lstrip("$")}
        accepted_results.update(result_tokens)
        supported_inputs.update(result_tokens)
    return accepted_results, failures


def check_article_numeric_findings(
    content_html: str,
    cards: list[dict[str, Any]],
    fetched: dict[str, str],
    calculations: Any = None,
    *,
    news_draft: bool = False,
) -> tuple[list[str], list[str]]:
    """Hard-check named-card/news numbers; generic warnings come from the card scan."""
    article_text = html_to_text(content_html)
    claims: dict[str, str] = {}
    for _start, _end, raw, token in iter_numeric_claims(article_text, key_numbers=True):
        claims.setdefault(token, raw)
    known_card_numbers = set().union(*(card_key_numbers(card) for card in cards))
    source_numbers = set().union(*(
        numeric_tokens(source_text, key_numbers=True)
        for source_text in fetched.values()
    ))
    _associated, _unassociated, illustrative_sentences, _named_claims = scan_card_numeric_claims(
        content_html, cards,
    )
    illustrative_numbers = set().union(*(
        set(_numeric_counter(sentence)) for sentence in illustrative_sentences
    ))
    calculated, calculation_failures = calculation_evidence(
        calculations if calculations is not None else [],
        known_card_numbers,
        source_numbers,
        illustrative_sentences,
    )
    math_operands = math_subtraction_operand_tokens(content_html)
    math_totals = signed_math_total_tokens(content_html)
    supported_numbers = known_card_numbers | source_numbers | calculated
    failures = [
        f"article numeric claim {raw.strip()} does not match relevant cards.json data, fetched source text, or verified calculation evidence"
        for token, raw in claims.items()
        if (
            token in math_totals
            and token not in calculated
        ) or (
            token not in math_totals
            and token not in supported_numbers
            and not signed_math_operand_is_supported(token, math_operands, supported_numbers)
            and (news_draft or token not in illustrative_numbers)
        )
    ]
    return calculation_failures + failures, []


def check_article_numeric_claims(
    content_html: str,
    cards: list[dict[str, Any]],
    fetched: dict[str, str],
    calculations: Any = None,
) -> list[str]:
    failures, _warnings = check_article_numeric_findings(
        content_html, cards, fetched, calculations,
    )
    return failures


def check_news_numeric_claims(
    content_html: str,
    cards: list[dict[str, Any]],
    fetched: dict[str, str],
    calculations: Any = None,
) -> list[str]:
    """Backward-compatible name for article-wide numeric verification."""
    failures, _warnings = check_article_numeric_findings(
        content_html, cards, fetched, calculations, news_draft=True,
    )
    return failures


def source_excerpts(
    fetched: dict[str, str],
    article_tokens: set[str],
    per_source_limit: int = 6000,
) -> dict[str, str]:
    """Keep source context around article-number matches for the LLM verifier."""
    excerpts: dict[str, str] = {}
    for url, source_text in fetched.items():
        windows: list[tuple[int, int]] = []
        for start, end, raw, token in iter_numeric_claims(source_text, key_numbers=True):
            claim_tokens = numeric_tokens(raw, key_numbers=True) or {token}
            if claim_tokens & article_tokens:
                windows.append((max(0, start - 350), min(len(source_text), end + 350)))
        merged: list[tuple[int, int]] = []
        for start, end in windows:
            if merged and start <= merged[-1][1] + 80:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        pieces: list[str] = []
        used = 0
        for start, end in merged:
            piece = re.sub(r"\s+", " ", source_text[start:end]).strip()
            remaining = per_source_limit - used
            if remaining <= 0:
                break
            pieces.append(piece[:remaining])
            used += min(len(piece), remaining)
        if not pieces:
            pieces = [re.sub(r"\s+", " ", source_text[:1200]).strip()]
        excerpts[url] = " […] ".join(piece for piece in pieces if piece)
    return excerpts


def is_internal_card_page_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    return hostname in {"practicalrewards.com", "www.practicalrewards.com"} and parsed.path.startswith("/card-pages/")


def claim_hint_missing_numbers(url: str, claim_hint: str, source_text: str) -> set[str]:
    expected = numeric_tokens(claim_hint, key_numbers=True)
    if is_internal_card_page_url(url):
        expected = {
            token for token in expected
            if not token.startswith(("date:", "date-year:"))
        }
    return expected - numeric_tokens(source_text, key_numbers=True)


def hero_findings(draft: dict[str, Any], cards_by_id: dict[Any, dict[str, Any]]) -> list[str]:
    hero = draft.get("hero")
    if hero is None:
        return []
    if not isinstance(hero, dict):
        return ["hero must be an object when present"]

    failures: list[str] = []
    unexpected = sorted(set(hero) - {"kicker", "stat", "label", "art"})
    if unexpected:
        failures.append("hero contains unexpected keys: " + ", ".join(unexpected))
    for field in ("kicker", "label"):
        field_value = hero.get(field)
        if not isinstance(field_value, str) or not field_value.strip():
            failures.append(f"hero.{field} must be non-empty plain text")
        elif PLAIN_TEXT_MARKUP_RE.search(field_value):
            failures.append(f"hero.{field} must be plain text without markup")

    stat = hero.get("stat")
    if not isinstance(stat, str) or not stat.strip():
        failures.append("hero.stat must be a non-empty string")
        return failures
    stat_tokens = numeric_tokens(stat, key_numbers=True)
    if not stat_tokens:
        failures.append(f"hero.stat {stat!r} does not contain a recognizable number")
        return failures

    article_tokens = numeric_tokens(
        html_to_text(str(draft.get("content_html", ""))),
        key_numbers=True,
    )
    relevant_card_tokens: set[str] = set()
    mentioned = set(draft.get("cards_mentioned", []))
    card_id: Any = None
    art = hero.get("art")
    if not isinstance(art, dict):
        failures.append("hero.art must be an object")
    elif art.get("type") == "card":
        card_id = art.get("card_id")
        if set(art) != {"type", "card_id"}:
            failures.append("card hero art must contain only type and card_id")
        if not isinstance(card_id, int) or isinstance(card_id, bool):
            failures.append("hero.art.card_id must be an integer")
        elif card_id not in cards_by_id:
            failures.append(f"hero.art.card_id {card_id} does not exist in cards.json")
        else:
            relevant_card_tokens = card_key_numbers(cards_by_id[card_id])
            if card_id not in mentioned:
                failures.append(f"hero.art.card_id {card_id} is not listed in cards_mentioned")
    elif art.get("type") == "brand":
        asset = art.get("asset")
        if set(art) != {"type", "asset"}:
            failures.append("brand hero art must contain only type and asset")
        if (
            not isinstance(asset, str)
            or Path(asset).name != asset
            or not (ROOT / "images" / "brands" / asset).is_file()
        ):
            failures.append("hero.art.asset does not exist in images/brands")
    elif art.get("type") == "none":
        if set(art) != {"type"}:
            failures.append("none hero art must contain only type")
    else:
        failures.append("hero.art.type must be card, brand, or none")

    if not stat_tokens & (article_tokens | relevant_card_tokens):
        card_context = (
            f" or cards.json data for hero.art.card_id {card_id}"
            if isinstance(card_id, int) and not isinstance(card_id, bool)
            else ""
        )
        failures.append(
            f"hero.stat {stat!r} does not match a numeric claim in content_html"
            f"{card_context}"
        )
    return failures


def verify() -> dict[str, Any]:
    draft = read_json(STATE / "draft.json")
    if not isinstance(draft, dict):
        raise ValueError("draft.json is missing or invalid")
    cards_all = read_json(ROOT / "cards.json", [])
    if not isinstance(cards_all, list):
        raise ValueError("cards.json must contain a list")
    mentioned = set(draft.get("cards_mentioned", []))
    content_html = str(draft.get("content_html", ""))
    content_text = html_to_text(content_html)
    cards_by_id = {card.get("id"): card for card in cards_all}
    unknown_ids = sorted(card_id for card_id in mentioned if card_id not in cards_by_id)
    cards = [cards_by_id[card_id] for card_id in mentioned if card_id in cards_by_id]
    content_card_ids = {
        mention[2].get("id") for mention in card_mentions(content_text, cards_all)
    }
    packet_failures: list[str] = []
    if unknown_ids:
        packet_failures.append("cards_mentioned contains unknown card IDs: " + ", ".join(map(str, unknown_ids)))
    omitted_ids = sorted(card_id for card_id in content_card_ids if card_id not in mentioned)
    if omitted_ids:
        packet_failures.append(
            "content_html mentions card IDs outside cards_mentioned/fact packet: "
            + ", ".join(map(str, omitted_ids))
        )
    sources = [source for source in draft.get("sources", []) if isinstance(source, dict)]
    brief = read_json(STATE / "todays-brief.json", {})
    post_type = brief.get("type", "evergreen") if isinstance(brief, dict) else "evergreen"

    failures: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    failures.extend(packet_failures)
    checks.append({
        "name": "card_fact_packet",
        "status": "fail" if packet_failures else "pass",
        "reasons": packet_failures,
    })

    hero_failures = hero_findings(draft, cards_by_id)
    failures.extend(hero_failures)
    checks.append({
        "name": "hero",
        "status": "fail" if hero_failures else "pass",
        "reasons": hero_failures,
    })

    fetched: dict[str, str] = {}
    source_failures: list[str] = []
    source_warnings: list[str] = []
    draft_source_urls = {
        validate_public_http_url(str(source.get("url", "")))
        for source in sources if source.get("url")
    }
    if post_type == "news":
        raw_brief_urls = brief.get("source_urls", []) if isinstance(brief, dict) else []
    else:
        topic_map = read_json(TOOLS / "content" / "topic-map.json", {})
        topics = topic_map.get("topics", []) if isinstance(topic_map, dict) else []
        topic = next(
            (item for item in topics if isinstance(item, dict) and item.get("slug") == brief.get("slug")),
            None,
        ) if isinstance(brief, dict) else None
        raw_brief_urls = topic.get("sources", []) if isinstance(topic, dict) else []
    if not isinstance(raw_brief_urls, list) or not all(isinstance(url, str) for url in raw_brief_urls):
        source_failures.append("assignment source URLs are not a list of URLs")
        raw_brief_urls = []
    brief_source_urls = {validate_public_http_url(url) for url in raw_brief_urls}
    if post_type == "news" and not sources:
        source_failures.append("news draft has no source URLs")
    if post_type == "news" and not brief_source_urls:
        source_failures.append("news brief has no source URLs")
    allowed_card_urls = {
        canonical_card_source_url(card)
        for card in cards
        if card.get("card_url")
    }
    missing_card_citations = sorted(allowed_card_urls - draft_source_urls)
    if missing_card_citations:
        source_failures.append(
            "draft omitted required card-page citation(s): " + ", ".join(missing_card_citations)
        )
    unexpected_urls = sorted(draft_source_urls - brief_source_urls - allowed_card_urls)
    if unexpected_urls:
        source_failures.append(
            f"{post_type} draft contains source URLs outside the supplied fact packet: "
            + ", ".join(unexpected_urls)
        )
    if post_type == "evergreen":
        missing_citations = sorted(brief_source_urls - draft_source_urls)
        if missing_citations:
            source_failures.append(
                "evergreen draft omitted attached source citation(s): " + ", ".join(missing_citations)
            )
    urls_to_fetch = draft_source_urls | brief_source_urls
    for url in sorted(urls_to_fetch):
        try:
            fetched[url] = fetch_article_text(url, timeout=15)
            if not fetched[url]:
                raise RuntimeError("no readable page text")
        except Exception as error:
            source_failures.append(f"source fetch failed for {url}: {error}")
    for source in sources:
        url = str(source.get("url", ""))
        if url not in fetched:
            continue
        missing = sorted(claim_hint_missing_numbers(
            url, str(source.get("claim_hint", "")), fetched[url],
        ))
        if missing:
            source_failures.append(
                f"source {url} does not contain key number(s) from its claim hint: {', '.join(missing)}"
            )
    article_number_failures, article_number_warnings = check_article_numeric_findings(
        content_html,
        cards,
        fetched,
        draft.get("calculations", []),
        news_draft=post_type == "news",
    )
    source_failures.extend(article_number_failures)
    source_warnings.extend(article_number_warnings)

    card_number_failures, card_number_warnings, illustrative_packet = check_card_number_findings(
        content_html, cards, list(fetched.values()), draft.get("calculations", []),
    )
    failures.extend(card_number_failures)
    warnings.extend(card_number_warnings)
    checks.append({
        "name": "card_numbers",
        "status": "fail" if card_number_failures else ("warn" if card_number_warnings else "pass"),
        "reasons": card_number_failures + card_number_warnings,
    })

    failures.extend(source_failures)
    warnings.extend(source_warnings)
    checks.append({
        "name": "source_reachability_and_numbers",
        "status": "fail" if source_failures else ("warn" if source_warnings else "pass"),
        "reasons": source_failures + source_warnings,
    })

    draft_grams = eight_grams(content_text)
    overlap_failures: list[str] = []
    overlap_details: list[dict[str, Any]] = []
    for url, source_text in fetched.items():
        shared = draft_grams & eight_grams(source_text)
        overlap_details.append({"url": url, "shared_8grams": len(shared)})
        if len(shared) > 2:
            samples = [" ".join(gram) for gram in sorted(shared)[:3]]
            overlap_failures.append(
                f"source echo for {url}: {len(shared)} shared 8-grams (examples: {' | '.join(samples)})"
            )
    failures.extend(overlap_failures)
    checks.append({
        "name": "source_8gram_overlap",
        "status": "fail" if overlap_failures else "pass",
        "reasons": overlap_failures,
        "details": overlap_details,
    })

    html_failures = validate_built_html(str(draft.get("slug", "")))
    failures.extend(html_failures)
    checks.append({"name": "built_html", "status": "fail" if html_failures else "pass", "reasons": html_failures})

    anecdote_failures = first_person_hard_rule_failures(content_html)
    failures.extend(anecdote_failures)
    checks.append({
        "name": "first_person_singular",
        "status": "fail" if anecdote_failures else "pass",
        "reasons": anecdote_failures,
    })

    prompt_template = (TOOLS / "prompts" / "verify.md").read_text(encoding="utf-8")
    article_tokens = numeric_tokens(content_text, key_numbers=True)
    excerpts = source_excerpts(fetched, article_tokens)
    prompt = fill_template(prompt_template, {
        "DRAFT_JSON": json.dumps(draft, ensure_ascii=False, indent=2),
        "CARDS_JSON": json.dumps([compact_card(card) for card in cards], ensure_ascii=False, indent=2),
        "SOURCE_EXCERPTS": json.dumps(excerpts, ensure_ascii=False, indent=2),
        "ILLUSTRATIVE_CLAIMS": json.dumps(illustrative_packet, ensure_ascii=False, indent=2),
    })
    verifier, llm_result, fallback_reason = independent_check(prompt)
    if fallback_reason:
        warnings.append(fallback_reason)
    llm_failures, llm_warnings = llm_review_findings(llm_result)
    failures.extend(llm_failures)
    warnings.extend(llm_warnings)
    checks.append({
        "name": "llm_review",
        "status": "fail" if llm_failures else ("warn" if llm_warnings else "pass"),
        "reasons": llm_failures + llm_warnings,
    })

    report = {
        "passed": not failures,
        "slug": draft.get("slug"),
        "type": post_type,
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "verifier": verifier,
        "llm_result": llm_result,
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
    }
    write_json(STATE / "verify-report.json", report)
    print("PASS" if report["passed"] else "FAIL")
    for reason in failures:
        print(f"- {reason}")
    return report


def main() -> int:
    try:
        report = verify()
    except Exception as error:
        report = {
            "passed": False,
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "verifier": "not-completed",
            "checks": [],
            "failures": [f"verification crashed: {type(error).__name__}: {error}"],
            "warnings": [],
        }
        write_json(STATE / "verify-report.json", report)
        print(report["failures"][0], file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
