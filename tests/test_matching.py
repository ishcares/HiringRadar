"""Tests for matching logic — no network, no Telegram, no Supabase."""

import sys
import json
from pathlib import Path

# Add root directory to path to allow direct imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from embeddings import calculate_cosine_similarity
from matching import (
    MATCH_THRESHOLD,
    ROLE_BONUS,
    INTERN_BONUS,
    build_match_reason,
    filter_by_job_type,
    get_experience_tag,
    group_jobs,
    is_internship,
    match_jobs_for_student,
    matches_role,
    _filter_fresher_jobs,
    _keyword_fallback_scores,
    _score_jobs,
)

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture(autouse=True)
def clear_embed_cache():
    from matching import _EMBED_CACHE
    _EMBED_CACHE.clear()
    yield
    _EMBED_CACHE.clear()

@pytest.fixture
def sample_jobs():
    with open(FIXTURES / "sample_jobs.json") as f:
        return json.load(f)


@pytest.fixture
def sample_students():
    with open(FIXTURES / "sample_students.json") as f:
        return json.load(f)


# ── Role matching ────────────────────────────────────────────────────────────

class TestMatchesRole:
    def test_backend_title_matches(self):
        assert matches_role("Backend Engineer", ["backend"]) is True

    def test_generic_swe_does_not_match_ml(self):
        assert matches_role("Software Engineer", ["ml"]) is False

    def test_empty_roles_matches_all(self):
        assert matches_role("Anything", []) is True

    def test_word_boundary_prevents_false_positive(self):
        assert matches_role("Analyst", ["ml"]) is False


# ── Job type filtering ───────────────────────────────────────────────────────

class TestFilterByJobType:
    def test_internship_only(self, sample_jobs):
        intern_job = sample_jobs[0]  # Software Engineer Intern
        fulltime_job = sample_jobs[1]  # Backend Engineer
        result = filter_by_job_type([intern_job, fulltime_job], "internship")
        assert len(result) == 1
        assert is_internship(result[0])

    def test_both_returns_all(self, sample_jobs):
        assert len(filter_by_job_type(sample_jobs, "both")) == len(sample_jobs)


# ── Experience tagging ───────────────────────────────────────────────────────

class TestExperienceTag:
    def test_intern_tagged_fresher(self):
        assert "Fresher" in get_experience_tag("Software Engineer Intern")

    def test_senior_tagged(self):
        assert "Senior" in get_experience_tag("Senior SDE II - Backend")

    def test_generic_swe_not_midlevel(self):
        tag = get_experience_tag("Software Engineer")
        assert tag == "💼 Software Engineer"
        assert "Mid-level" not in tag


# ── Fresher filtering ────────────────────────────────────────────────────────

class TestFresherFilter:
    def test_senior_filtered_for_2026_grad(self, sample_jobs):
        jobs = [j for j in sample_jobs if matches_role(j["title"], ["backend"])]
        filtered = _filter_fresher_jobs(jobs, grad_year=2026, current_year=2025)
        titles = [j["title"] for j in filtered]
        assert "Senior SDE II - Backend" not in titles

    def test_generic_swe_kept_for_fresher(self, sample_jobs):
        groww = next(j for j in sample_jobs if j["company"] == "Groww")
        filtered = _filter_fresher_jobs([groww], grad_year=2026, current_year=2025)
        assert len(filtered) == 1

    def test_midlevel_filtered_for_fresher(self, sample_jobs):
        mid = next(j for j in sample_jobs if "Mid-level" in j["title"])
        filtered = _filter_fresher_jobs([mid], grad_year=2026, current_year=2025)
        assert len(filtered) == 0


# ── Scoring with mock embeddings ─────────────────────────────────────────────

def _mock_embed_fn(texts):
    """Return unit vectors based on text content keywords to simulate semantic similarity."""
    vectors = []
    for text in texts:
        t = text.lower()
        if "backend" in t:
            vectors.append([1.0, 0.0, 0.0])
        elif "ml" in t or "machine learning" in t:
            vectors.append([0.0, 1.0, 0.0])
        elif "frontend" in t or "react" in t:
            vectors.append([0.0, 0.0, 1.0])
        else:
            vectors.append([0.5, 0.5, 0.5])
    return vectors


class TestScoring:
    def test_role_bonus_increases_score(self, sample_jobs):
        student_with = {
            "graduation_year": 2026,
            "skills": ["Python"],
            "preferred_roles": ["backend"],
            "job_type": "both",
        }
        student_without = {
            "graduation_year": 2026,
            "skills": ["Python"],
            "preferred_roles": ["ml"],
            "job_type": "both",
        }
        backend_job = next(j for j in sample_jobs if j["title"] == "Backend Engineer")
        scores_with_bonus, _ = _score_jobs([backend_job], student_with, ["backend"], _mock_embed_fn)
        scores_no_bonus, _ = _score_jobs([backend_job], student_without, ["ml"], _mock_embed_fn)
        assert scores_with_bonus[0] > scores_no_bonus[0]

    def test_hf_fallback_uses_keyword_only_not_silent_pass(self, sample_jobs):
        """When HF API fails, jobs should be scored by keywords only —
        NOT silently assigned 0.3 which would pass threshold for everything.
        A job that does NOT match the role keywords must score 0.0.
        """
        student = {
            "graduation_year": 2026,
            "skills": ["Python"],
            "preferred_roles": ["backend"],
            "job_type": "both",
        }
        # ML Engineer job — does NOT match backend role keywords
        ml_job = next(j for j in sample_jobs if "Machine Learning" in j["title"])
        scores = _keyword_fallback_scores([ml_job], ["backend"], 2026, 2026)
        assert scores[0] == 0.0, "Non-matching job must not silently pass threshold"

        # Backend Engineer job — DOES match backend keywords
        backend_job = next(j for j in sample_jobs if j["title"] == "Backend Engineer")
        scores = _keyword_fallback_scores([backend_job], ["backend"], 2026, 2026)
        assert scores[0] == ROLE_BONUS, "Role-matching job should get ROLE_BONUS"

        # Full end-to-end: empty embed_fn triggers fallback, results are filtered
        matched = match_jobs_for_student(
            student, sample_jobs, embed_fn=lambda texts: []
        )
        matched_titles = [j["title"] for j, _ in matched]
        assert "Machine Learning Engineer" not in matched_titles, (
            "ML jobs must NOT appear for backend student in fallback mode"
        )


# ── End-to-end match (mocked embeddings) ─────────────────────────────────────

class TestMatchJobsForStudent:
    def test_backend_intern_persona(self, sample_jobs, sample_students):
        student = sample_students[0]
        matched = match_jobs_for_student(student, sample_jobs, embed_fn=_mock_embed_fn)
        assert len(matched) > 0
        titles = [j["title"] for j, _ in matched]
        assert "Senior SDE II - Backend" not in titles
        assert any("Intern" in t for t in titles)

    def test_ml_persona_gets_ml_jobs(self, sample_jobs, sample_students):
        student = sample_students[1]
        matched = match_jobs_for_student(student, sample_jobs, embed_fn=_mock_embed_fn)
        titles = [j["title"] for j, _ in matched]
        assert any("Machine Learning" in t or "ML" in t for t in titles)

    def test_threshold_filters_low_scores(self, sample_jobs, sample_students):
        student = sample_students[0]

        def low_similarity_embed(texts):
            return [[1, 0, 0]] + [[0, 1, 0]] * (len(texts) - 1)

        matched = match_jobs_for_student(
            student, sample_jobs, threshold=0.45, embed_fn=low_similarity_embed
        )
        # Orthogonal vectors -> blended score is 0.30 + 0.10 boost = 0.40 < 0.45 -> no match
        assert len(matched) == 0

    def test_empty_when_no_role_match(self, sample_jobs):
        student = {
            "graduation_year": 2026,
            "skills": ["Python"],
            "preferred_roles": ["ios"],
            "job_type": "both",
        }
        # Only iOS job in fixtures
        matched = match_jobs_for_student(student, sample_jobs, embed_fn=_mock_embed_fn)
        assert len(matched) <= 1

    def test_frontend_intern_persona_matches(self, sample_jobs):
        """Persona 3: frontend + internship. Fixtures now include a
        'Frontend Engineer Intern' entry, so this persona must get ≥1 match.
        """
        student = {
            "name": "2027 Frontend Intern",
            "graduation_year": 2027,
            "skills": ["React", "JavaScript"],
            "preferred_roles": ["frontend"],
            "job_type": "internship",
        }
        matched = match_jobs_for_student(student, sample_jobs, embed_fn=_mock_embed_fn)
        assert len(matched) >= 1, "Frontend intern persona must match ≥1 job with fixture data"
        titles = [j["title"] for j, _ in matched]
        assert any("Frontend" in t for t in titles)

    def test_env_threshold_is_respected(self, sample_jobs):
        """Passing an explicit threshold to match_jobs_for_student overrides the env default."""
        student = {
            "graduation_year": 2026,
            "skills": ["Python"],
            "preferred_roles": ["backend"],
            "job_type": "both",
        }

        def low_embed(texts):
            return [[1, 0, 0]] + [[0, 1, 0]] * (len(texts) - 1)

        # At threshold (0.45) backend jobs score 0.40 -> no match
        no_match = match_jobs_for_student(student, sample_jobs, threshold=0.45, embed_fn=low_embed)
        assert len(no_match) == 0

        # At lowered threshold (0.35) the same jobs score 0.40 -> match
        with_match = match_jobs_for_student(student, sample_jobs, threshold=0.35, embed_fn=low_embed)
        assert len(with_match) > 0


# ── Utilities ────────────────────────────────────────────────────────────────

class TestUtilities:
    def test_group_jobs_deduplicates(self, sample_jobs):
        dup = sample_jobs[0]
        grouped = group_jobs([dup, dup])
        assert len(grouped) == 1
        assert grouped[0]["count"] == 2

    def test_cosine_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert calculate_cosine_similarity(v, v) == pytest.approx(1.0)

    def test_build_match_reason_includes_role(self, sample_jobs, sample_students):
        student = sample_students[0]
        job = sample_jobs[1]  # Backend Engineer
        reason = build_match_reason(job, student)
        assert "Backend" in reason or "backend" in reason.lower()
