import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from ai_agent import compute_skills_match

def test_empty_required_skills_does_not_default_to_100():
    """SDE I bug: empty required-skills list should NOT yield 100% match"""
    required_skills = []
    matched_skills = []
    result = compute_skills_match(required_skills, matched_skills)
    assert result == 0.0

def test_zero_matched_of_many_required_yields_zero():
    """MLDOps bug (this one worked correctly) — regression guard"""
    required_skills = ["agentic systems", "cloud computing", "ivr", "crm"]
    matched_skills = []
    result = compute_skills_match(required_skills, matched_skills)
    assert result == 0.0

def test_partial_match_is_proportional():
    required_skills = ["python", "sql", "aws", "docker"]
    matched_skills = ["python", "sql"]
    result = compute_skills_match(required_skills, matched_skills)
    assert result == 0.5

def test_no_contradiction_between_pct_and_matched_list():
    """If matched_skills is empty, overall skills_match_pct must be 0 or None, never >0"""
    for required, matched in [([], []), (["x","y"], [])]:
        pct = compute_skills_match(required, matched)
        assert pct in (0.0, None)
