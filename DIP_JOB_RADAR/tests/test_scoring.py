from types import SimpleNamespace
from radar.scoring import score_job


KEYWORDS = {
    "location": {"required": ["ahmedabad"], "nearby_allowed": False},
    "primary_roles": ["ui/ux designer", "product designer", "ui designer"],
    "bridge_roles": ["graphic designer ui ux"],
    "skills": ["figma", "wireframes", "prototype", "design system"],
    "product_signals": ["product design", "saas"],
    "hiring_signals": ["hiring", "looking for", "join our team"],
    "hashtags": ["#hiring", "#uiuxdesigner"],
    "exclude_terms": ["senior product designer", "internship", "video editor"]
}


def test_good_ahmedabad_uiux_job_scores_well():
    job = SimpleNamespace(
        title="UI/UX Designer",
        url="https://example.com/job",
        description="Hiring UI/UX Designer in Ahmedabad. Figma, wireframes and prototypes required.",
        source="example.com"
    )
    result = score_job(job, KEYWORDS)
    assert result.score >= 60
    assert "Ahmedabad" in result.reasons


def test_non_ahmedabad_job_is_penalized():
    job = SimpleNamespace(
        title="UI/UX Designer",
        url="https://example.com/job",
        description="Hiring in Mumbai. Figma required.",
        source="example.com"
    )
    result = score_job(job, KEYWORDS)
    assert result.score < 60


def test_senior_role_is_penalized():
    job = SimpleNamespace(
        title="Senior Product Designer",
        url="https://example.com/job",
        description="Ahmedabad hiring for senior product designer.",
        source="example.com"
    )
    result = score_job(job, KEYWORDS)
    assert result.score < 60
