import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ScoredJob:
    score: int
    reasons: list[str]
    negative_reasons: list[str]


def _text(job) -> str:
    return " ".join([
        job.title or "",
        job.description or "",
        job.url or "",
        job.source or "",
    ]).lower()


def _contains(text: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if " " in phrase or "/" in phrase or "&" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def score_job(job, keywords: dict) -> ScoredJob:
    text = _text(job)
    score = 0
    reasons = []
    negative = []

    # Location is mandatory, not just a bonus.
    location_hit = any(_contains(text, x) for x in keywords["location"]["required"])
    if location_hit:
        score += 30
        reasons.append("Ahmedabad")
    else:
        score -= 50
        negative.append("No Ahmedabad signal")

    if any(_contains(text, x) for x in keywords["primary_roles"]):
        score += 25
        reasons.append("target role")

    if any(_contains(text, x) for x in keywords["bridge_roles"]):
        score += 15
        reasons.append("graphic/UI bridge role")

    skill_hits = [x for x in keywords["skills"] if _contains(text, x)]
    if skill_hits:
        score += min(10, len(skill_hits) * 2)
        reasons.append("skills: " + ", ".join(skill_hits[:4]))

    product_hits = [x for x in keywords["product_signals"] if _contains(text, x)]
    if product_hits:
        score += 5
        reasons.append("product-design signal")

    hiring_hits = [x for x in keywords["hiring_signals"] if _contains(text, x)]
    if hiring_hits:
        score += 10
        reasons.append("hiring language")

    if any(_contains(text, x) for x in keywords["hashtags"]):
        score += 5
        reasons.append("hiring hashtag")

    for term in keywords["exclude_terms"]:
        if _contains(text, term):
            score -= 30
            negative.append(term)

    # Very senior wording gets an extra penalty.
    if any(_contains(text, x) for x in [
        "senior", "lead", "manager", "principal", "head of design"
    ]):
        score -= 10
        negative.append("seniority signal")

    score = max(0, min(100, score))
    return ScoredJob(score=score, reasons=reasons, negative_reasons=negative)
