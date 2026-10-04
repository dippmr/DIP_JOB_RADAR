from types import SimpleNamespace
from radar.scoring import score_job
K={"location":{"required":["ahmedabad"]},"primary_roles":["ui/ux designer","product designer"],"bridge_roles":["graphic designer ui ux"],"skills":["figma","wireframe","design system"],"product_signals":["product design"],"hiring_signals":["hiring","looking for"],"hashtags":["#hiringdesigner"],"exclude_terms":["senior product designer","internship","trainee"]}
def j(t,d=""): return SimpleNamespace(title=t,description=d,url="https://example.com/job",source="Example")
def test_good_job(): assert score_job(j("Junior UI/UX Designer — Ahmedabad","We are hiring. Figma, wireframes, product design."),K).score>=60
def test_wrong_city(): assert score_job(j("UI/UX Designer — Mumbai","Hiring Figma designer"),K).score<60
def test_senior(): assert score_job(j("Senior Product Designer — Ahmedabad","Hiring"),K).score<60
