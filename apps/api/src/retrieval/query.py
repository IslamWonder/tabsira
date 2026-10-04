"""
The words of a concept query, as lexical search looks for them.

A query («الرحمة بالحيوان») is folded the way the search copies were
(`src.scripture.text.search_copy`), its particles are dropped, and each
remaining word is reduced to a light stem: a leading conjunction (و، ف) and the
article with its fused prepositions (ال، بال، كال، فال، وال، لل) are removed
when at least three letters remain. Nothing is guessed about roots: the stem is
matched as a prefix, against every way the texts attach clitics to a word
(`CLITIC_PREFIXES`), so «رحم» finds «والرحمه» and «برحمته» but a short stem
that would match half the corpus is not kept.
"""

from __future__ import annotations

import re

from src.scripture.text import search_copy

MIN_STEM = 3
MAX_TERMS = 8

# Folded particles, pronouns and common verbs of saying: they match everything and mean nothing.
STOPWORDS = frozenset(
    [
        "من",
        "في",
        "علي",
        "الي",
        "عن",
        "ما",
        "لا",
        "ان",
        "او",
        "ثم",
        "قد",
        "هو",
        "هي",
        "هم",
        "هن",
        "انت",
        "انا",
        "نحن",
        "الذي",
        "التي",
        "الذين",
        "اللذين",
        "اللاتي",
        "كل",
        "بين",
        "عند",
        "حتي",
        "مع",
        "كما",
        "بعد",
        "قبل",
        "دون",
        "غير",
        "ذلك",
        "هذا",
        "هذه",
        "تلك",
        "هولاء",
        "له",
        "لها",
        "لهم",
        "لنا",
        "لك",
        "به",
        "بها",
        "بهم",
        "فيه",
        "فيها",
        "فيهم",
        "منه",
        "منها",
        "منهم",
        "عليه",
        "عليها",
        "عليهم",
        "الا",
        "بل",
        "اذا",
        "اذ",
        "يا",
        "لم",
        "لن",
        "لو",
        "ولا",
        "ولو",
        "مما",
        "عما",
        "ممن",
        "كان",
        "كانت",
        "يكون",
        "تكون",
        "قال",
        "قالت",
        "يقول",
        "قالوا",
        "ليس",
        "اي",
        "ايضا",
        "وهو",
        "وهي",
        "وما",
        "ومن",
        "وفي",
        "وعلي",
        "والي",
        "وعن",
        "وان",
        "وكل",
        "ثم",
        "حين",
        "حيث",
        "كيف",
        "لماذا",
        "متي",
        "هل",
    ]
)
_CONJUNCTIONS = ("و", "ف")
# Longest first, so «بال» is removed whole and not as «ب» then «ال».
_ARTICLES = ("وبال", "فبال", "وال", "فال", "بال", "كال", "لل", "ال")
# Every way a stem may begin a word of the folded texts: alone, after the
# article, after a conjunction or a preposition, or both.
CLITIC_PREFIXES = (
    "",
    "ال",
    "و",
    "ف",
    "ب",
    "ك",
    "ل",
    "وال",
    "فال",
    "بال",
    "كال",
    "لل",
    "وب",
    "ول",
    "فب",
    "فل",
    "وبال",
    "ولل",
    "س",
    "وس",
)
_WORD = re.compile(r"^[ء-ي0-9a-z]+$")


def stem(word: str) -> str:
    """Return the light stem of one folded word, or the word itself when too little would remain."""
    for conjunction in _CONJUNCTIONS:
        if word.startswith(conjunction) and len(word) - len(conjunction) >= MIN_STEM + 1:
            rest = word[len(conjunction) :]
            if rest not in STOPWORDS:
                word = rest
            break
    for article in _ARTICLES:
        if word.startswith(article) and len(word) - len(article) >= MIN_STEM:
            return word[len(article) :]
    return word


def query_terms(text: str) -> list[str]:
    """Return the distinct stems of a query, in order, without particles, at most `MAX_TERMS`."""
    terms: list[str] = []
    for word in search_copy(text).lower().split():
        if word in STOPWORDS or not _WORD.match(word):
            continue
        stemmed = stem(word)
        if len(stemmed) >= MIN_STEM and stemmed not in STOPWORDS and stemmed not in terms:
            terms.append(stemmed)
    return terms[:MAX_TERMS]


def prefix_query(term: str) -> str:
    """Return the `to_tsquery('simple', ...)` text that finds `term` behind any clitic."""
    return " | ".join(f"{prefix}{term}:*" for prefix in CLITIC_PREFIXES)
