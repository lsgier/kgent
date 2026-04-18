from orchestrator import _pick_canonical
from models import Person


def make_person(iri: str, **kwargs) -> Person:
    defaults = dict(name="Test", github_username="test")
    return Person(iri=iri, **{**defaults, **kwargs})


class TestPickCanonical:
    def test_prefers_more_complete_person(self):
        sparse = make_person("https://open-pulse.epfl.ch/person/sparse")
        rich = make_person(
            "https://open-pulse.epfl.ch/person/rich",
            email="rich@epfl.ch",
            orcid="0000-0001-2345-6789",
            infoscience_id="abc123",
        )
        persons = {p.iri: p for p in [sparse, rich]}
        assert _pick_canonical(list(persons), persons) == rich.iri

    def test_tiebreak_prefers_shorter_iri(self):
        short = "https://ex.com/a"
        long = "https://ex.com/longer-iri"
        persons = {iri: make_person(iri) for iri in [short, long]}
        assert _pick_canonical(list(persons), persons) == short

    def test_tiebreak_lexicographic_when_same_length(self):
        a_iri = "https://ex.com/aaaa"
        b_iri = "https://ex.com/bbbb"
        persons = {iri: make_person(iri) for iri in [a_iri, b_iri]}
        assert _pick_canonical(list(persons), persons) == a_iri

    def test_single_entity_returns_itself(self):
        iri = "https://open-pulse.epfl.ch/person/only"
        persons = {iri: make_person(iri)}
        assert _pick_canonical([iri], persons) == iri
