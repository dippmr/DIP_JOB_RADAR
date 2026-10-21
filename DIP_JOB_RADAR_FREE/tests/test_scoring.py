from radar.scoring import (
    LOCATION_NONE,
    LOCATION_STRONG,
    LOCATION_WEAK,
    contains,
    location_level,
    score_job,
)
from tests.helpers import make_job

K = {
    "location": {"required": ["ahmedabad"]},
    "primary_roles": ["ui/ux designer", "product designer"],
    "bridge_roles": ["graphic designer ui ux"],
    "skills": ["figma", "wireframe", "design system"],
    "product_signals": ["product design"],
    "hiring_signals": ["hiring", "looking for"],
    "hashtags": ["#hiringdesigner"],
    "exclude_terms": ["senior product designer", "internship", "trainee", "intern"],
}


def test_good_job():
    job = make_job(
        "Junior UI/UX Designer — Ahmedabad",
        "We are hiring. Figma, wireframes, product design.",
    )
    assert score_job(job, K).score >= 60


def test_wrong_city_scores_zero():
    scored = score_job(make_job("UI/UX Designer — Mumbai", "Hiring Figma designer"), K)
    assert scored.score == 0
    assert scored.location == LOCATION_NONE


def test_senior_role_is_rejected():
    scored = score_job(make_job("Senior Product Designer — Ahmedabad", "Hiring"), K)
    assert scored.score < 60


def test_hashtags_are_matched():
    # Regression: "#hiringdesigner" used to be impossible to match.
    assert contains("we are #hiringdesigner in ahmedabad", "#hiringdesigner")
    assert contains("#hiringdesigner", "#hiringdesigner")
    job = make_job("Product Designer Ahmedabad #hiringdesigner")
    assert "Hiring hashtag" in score_job(job, K).reasons


def test_plurals_match():
    assert contains("we use wireframes daily", "wireframe")
    assert not contains("we use wireframed layouts", "wireframe")


def test_lead_generation_is_not_a_seniority_signal():
    job = make_job("Product Designer — Ahmedabad", "Hiring. Lead generation pages.")
    assert score_job(job, K).negative_reasons == []


def test_social_media_manager_is_not_a_seniority_signal():
    job = make_job(
        "Product Designer — Ahmedabad", "Hiring. Report to social media manager."
    )
    assert score_job(job, K).negative_reasons == []


def test_real_leadership_titles_are_penalised():
    job = make_job("Lead Designer — Ahmedabad", "Hiring Product Designer")
    scored = score_job(job, K)
    assert "Senior/leadership signal" in scored.negative_reasons


def test_senior_word_is_not_penalised_twice():
    base = score_job(make_job("Product Designer — Ahmedabad", "Hiring"), K).score
    senior = score_job(
        make_job("Senior Product Designer — Ahmedabad", "Hiring"), K
    ).score
    assert base - senior == 30  # one exclusion penalty, no extra seniority penalty


def test_intern_excluded_but_international_is_not():
    intern = score_job(make_job("UI/UX Designer Intern — Ahmedabad", "Hiring"), K)
    assert any("intern" in x for x in intern.negative_reasons)
    intl = score_job(make_job("UI/UX Designer — Ahmedabad", "International clients"), K)
    assert intl.negative_reasons == []


def test_location_in_text_is_strong():
    job = make_job("UI/UX Designer — Ahmedabad")
    assert location_level(job, K) == LOCATION_STRONG


def test_location_only_in_query_is_weak_and_scores_lower():
    strong = make_job("UI/UX Designer hiring", "Figma", query="")
    weak = make_job("UI/UX Designer hiring", "Figma", query='"Ahmedabad" hiring')
    strong.title += " Ahmedabad"
    assert location_level(weak, K) == LOCATION_WEAK
    weak_score = score_job(weak, K)
    strong_score = score_job(strong, K)
    assert weak_score.score > 0
    assert strong_score.score - weak_score.score == 10
    assert weak_score.location == LOCATION_WEAK


def test_score_is_always_between_0_and_100():
    perfect = make_job(
        "Junior UI/UX Designer Ahmedabad hiring #hiringdesigner",
        "graphic designer ui ux figma wireframe design system product design looking for",
    )
    assert 0 <= score_job(perfect, K).score <= 100
