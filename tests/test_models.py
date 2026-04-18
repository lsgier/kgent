import pytest
from pydantic import ValidationError

from models import Person


def make_person(**kwargs) -> Person:
    defaults = dict(iri="https://open-pulse.epfl.ch/person/1", name="Alice", github_username="alice")
    return Person(**{**defaults, **kwargs})


class TestPersonMerge:
    def test_keeps_canonical_iri(self):
        canonical = make_person(iri="https://open-pulse.epfl.ch/person/canonical")
        duplicate = make_person(iri="https://open-pulse.epfl.ch/person/duplicate")
        merged = canonical.merge(duplicate)
        assert merged.iri == canonical.iri

    def test_canonical_attribute_takes_precedence(self):
        canonical = make_person(email="canonical@epfl.ch")
        duplicate = make_person(email="duplicate@epfl.ch")
        merged = canonical.merge(duplicate)
        assert merged.email == "canonical@epfl.ch"

    def test_fills_missing_attribute_from_duplicate(self):
        canonical = make_person(email=None)
        duplicate = make_person(email="alice@epfl.ch")
        merged = canonical.merge(duplicate)
        assert merged.email == "alice@epfl.ch"

    def test_unions_list_fields(self):
        canonical = make_person(has_contribution=["https://c/1", "https://c/2"])
        duplicate = make_person(has_contribution=["https://c/2", "https://c/3"])
        merged = canonical.merge(duplicate)
        assert set(merged.has_contribution) == {"https://c/1", "https://c/2", "https://c/3"}

    def test_deduplicates_list_fields(self):
        canonical = make_person(owns=["https://repo/a"])
        duplicate = make_person(owns=["https://repo/a"])
        merged = canonical.merge(duplicate)
        assert merged.owns.count("https://repo/a") == 1

    def test_all_list_fields_are_unioned(self):
        canonical = make_person(has_membership=["https://m/1"])
        duplicate = make_person(has_membership=["https://m/2"])
        merged = canonical.merge(duplicate)
        assert set(merged.has_membership) == {"https://m/1", "https://m/2"}


class TestPersonValidation:
    def test_requires_at_least_one_identifier(self):
        with pytest.raises(ValidationError, match="at least one"):
            Person(iri="https://open-pulse.epfl.ch/person/1", name="No ID")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            make_person(email="not-an-email")

    def test_invalid_orcid_rejected(self):
        with pytest.raises(ValidationError):
            make_person(orcid="0000-0000-0000-000")  # missing last digit

    def test_valid_orcid_accepted(self):
        p = make_person(orcid="0000-0001-2345-678X")
        assert p.orcid == "0000-0001-2345-678X"
