# -*- coding: utf-8 -*-
"""Small helpers for pinyin-aware UI search."""
from functools import lru_cache

try:
    from pypinyin import Style, lazy_pinyin
except Exception:
    Style = None
    lazy_pinyin = None


def split_search_terms(text):
    return [term.strip().lower() for term in str(text or "").split() if term.strip()]


@lru_cache(maxsize=8192)
def pinyin_variants(value):
    text = str(value or "").strip()
    if not text or not lazy_pinyin:
        return ()
    try:
        full = "".join(lazy_pinyin(text, style=Style.NORMAL, errors="ignore")).lower()
        initials = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER, errors="ignore")).lower()
    except Exception:
        return ()
    return tuple(variant for variant in (full, initials) if variant)


def text_matches(keyword, *values):
    keyword = str(keyword or "").strip().lower()
    if not keyword:
        return True
    for value in values:
        text = str(value or "").strip().lower()
        if keyword in text:
            return True
        if any(keyword in variant for variant in pinyin_variants(value)):
            return True
    return False


def all_terms_match(terms, *values):
    terms = [str(term or "").strip().lower() for term in terms if str(term or "").strip()]
    return all(text_matches(term, *values) for term in terms)


def any_terms_match(terms, *values):
    terms = [str(term or "").strip().lower() for term in terms if str(term or "").strip()]
    return not terms or any(text_matches(term, *values) for term in terms)


def match_score(search_text, terms, *values):
    terms = [str(term or "").strip().lower() for term in terms if str(term or "").strip()]
    full_hit = 1 if search_text and text_matches(search_text, *values) else 0
    hit_count = sum(1 for term in terms if text_matches(term, *values))
    return full_hit, hit_count
