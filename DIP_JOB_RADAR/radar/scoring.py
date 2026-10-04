from __future__ import annotations
from dataclasses import dataclass
import re
@dataclass
class ScoredJob:
    score: int
    reasons: list[str]
    negative_reasons: list[str]
def _text(job):
    return " ".join([getattr(job,"title",""), getattr(job,"description",""), getattr(job,"url",""), getattr(job,"source","")]).lower()
def _contains(text, term):
    term = term.lower().strip()
    if not term: return False
    if any(ch in term for ch in ["/", "&", "'", "-", " "]): return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))
def score_job(job, keywords):
    text=_text(job); score=0; reasons=[]; negative=[]
    if any(_contains(text,x) for x in keywords["location"]["required"]): score+=30; reasons.append("Ahmedabad match")
    else: score-=50; negative.append("No Ahmedabad signal")
    primary=[x for x in keywords["primary_roles"] if _contains(text,x)]
    if primary: score+=25; reasons.append("Target role: "+primary[0])
    bridge=[x for x in keywords["bridge_roles"] if _contains(text,x)]
    if bridge: score+=15; reasons.append("Graphic → UI/UX bridge role")
    skills=[x for x in keywords["skills"] if _contains(text,x)]
    if skills: score+=min(10,2*len(skills)); reasons.append("Skills: "+", ".join(skills[:4]))
    products=[x for x in keywords["product_signals"] if _contains(text,x)]
    if products: score+=5; reasons.append("Product signal")
    hiring=[x for x in keywords["hiring_signals"] if _contains(text,x)]
    if hiring: score+=10; reasons.append("Hiring signal")
    tags=[x for x in keywords["hashtags"] if _contains(text,x)]
    if tags: score+=5; reasons.append("Hiring hashtag")
    for term in [x for x in keywords["exclude_terms"] if _contains(text,x)]: score-=30; negative.append(f"Excluded: {term}")
    if any(_contains(text,x) for x in ["senior","lead","manager","head of design","principal"]): score-=10; negative.append("Senior/leadership signal")
    return ScoredJob(max(0,min(100,score)), reasons, negative)
