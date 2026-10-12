"""Local, dependency-free AI helpers.

Lexicon-based sentiment analysis, review summarisation, and report-category
suggestions. No external API — everything here is deterministic and offline,
which keeps the student-prototype scope (no keys, no cost, no network).
"""

from __future__ import annotations

import re
from collections import Counter

from scamguard.models import ReportCategory, Review

POSITIVE_WORDS = {
    "genuine", "great", "good", "excellent", "trusted", "trustworthy",
    "fast", "quick", "smooth", "legit", "legitimate", "recommend",
    "recommended", "reliable", "honest", "amazing", "awesome", "perfect",
    "satisfied", "helpful", "professional", "original", "best", "love",
    "easy", "friendly",
}

NEGATIVE_WORDS = {
    "scam", "scammer", "scams", "fraud", "fake", "ghosted", "ghost",
    "blocked", "worst", "terrible", "horrible", "cheated", "cheat",
    "stolen", "steal", "waste", "delayed", "rude", "dishonest",
    "useless", "never",
}

NEGATORS = {"not", "no", "never", "without", "cannot"}

TOPIC_FAMILIES = {
    "delivery": ["deliver", "parcel", "arrive", "shipping", "shipped"],
    "payment": ["pay", "paid", "payment", "money", "transfer", "bank", "fee"],
    "refund": ["refund", "back"],
    "quality": ["quality", "original", "fake", "replica", "counterfeit"],
    "communication": ["reply", "replied", "response", "communicat", "chat"],
    "price": ["price", "expensive", "cheap", "overcharged"],
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    ReportCategory.FAKE_PAYMENT_REQUEST.value: (
        "advance", "payment", "fee", "transfer", "money", "paid",
        "paying", "send", "sent", "deposit",
    ),
    ReportCategory.NON_DELIVERY.value: (
        "deliver", "delivery", "received", "receive", "parcel",
        "package", "arrive", "arrived", "shipping", "shipped",
    ),
    ReportCategory.FAKE_SELLER.value: (
        "fake", "replica", "counterfeit", "fraud", "scam", "scammer",
        "fraudulent", "cheated",
    ),
    ReportCategory.PHISHING.value: (
        "otp", "link", "password", "login", "credential", "verification",
        "phishing", "click", "clicked", "code",
    ),
}

# Deterministic tie-break order when two categories score the same.
_CATEGORY_PRIORITY = (
    ReportCategory.PHISHING.value,
    ReportCategory.FAKE_PAYMENT_REQUEST.value,
    ReportCategory.NON_DELIVERY.value,
    ReportCategory.FAKE_SELLER.value,
)

_TOKEN_RE = re.compile(r"[a-z']+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _is_negator(token: str) -> bool:
    return token in NEGATORS or token.endswith("n't")


def sentiment_score(text: str) -> int:
    """Return a net sentiment score: positive words minus negatives.

    A sentiment word within two tokens after a negator flips sign
    ("not good" scores negative, "not bad" scores positive).
    """
    toks = _tokens(text)
    score = 0
    for i, token in enumerate(toks):
        negated = any(
            _is_negator(toks[j]) for j in (i - 1, i - 2) if j >= 0
        )
        if token in POSITIVE_WORDS:
            score += -1 if negated else 1
        elif token in NEGATIVE_WORDS:
            score += 1 if negated else -1
    return score


def review_tone(text: str, rating: int = 3) -> str:
    """Classify a review as 'positive', 'negative', or 'neutral'.

    Combines the text's sentiment with the star rating: a 1–2 star
    review reads negative and a 4–5 star review reads positive unless
    the words are strongly the other way.
    """
    score = sentiment_score(text) + (rating - 3)
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


def _top_topics(texts: list[str]) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        toks = _tokens(text)
        for topic, family in TOPIC_FAMILIES.items():
            hits = sum(1 for t in toks if any(t.startswith(w) for w in family))
            if hits:
                counts[topic] += hits
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [topic for topic, _ in ranked[:3]]


def summarize_reviews(reviews: list[Review]) -> dict:
    """Build the 'what people say' insight for a list of reviews."""
    texts = [r.body for r in reviews]
    total = len(texts)
    if total == 0:
        return {
            "total": 0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "topics": [],
            "sentence": "No reviews yet — nothing to summarize.",
        }

    tones = Counter(review_tone(t, r.rating) for t, r in zip(texts, reviews))
    positive = tones.get("positive", 0)
    neutral = tones.get("neutral", 0)
    negative = tones.get("negative", 0)
    topics = _top_topics(texts)

    sentence = f"{positive} of {total} reviews are positive."
    if topics:
        sentence += f" People mostly mention: {', '.join(topics)}."

    return {
        "total": total,
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "topics": topics,
        "sentence": sentence,
    }


def suggest_category(text: str) -> str | None:
    """Suggest a ReportCategory value for a free-text description.

    Returns None when no keyword matches anything (no confident guess).
    """
    toks = _tokens(text)
    if not toks:
        return None

    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(
            1 for t in toks if any(t.startswith(k) for k in keywords)
        )

    best = max(scores.values())
    if best == 0:
        return None
    for category in _CATEGORY_PRIORITY:
        if scores[category] == best:
            return category
    return None
