"""Post-call extraction tolerates the shapes the model actually returns."""

from app.domain.real_estate.extraction import Extraction


def test_a_bare_value_becomes_a_one_item_list():
    e = Extraction.model_validate({"questions_asked": "Is there a swimming pool?", "bhk": 2})
    assert e.questions_asked == ["Is there a swimming pool?"] and e.bhk == [2]


def test_empty_markers_become_empty_lists():
    for empty in (None, "", "null", "NA", []):
        e = Extraction.model_validate({"questions_asked": empty, "unanswered_questions": empty, "bhk": empty})
        assert e.questions_asked == [] and e.unanswered_questions == [] and e.bhk == []


def test_one_bad_list_field_does_not_lose_the_rest():
    e = Extraction.model_validate({"summary": "Wants a 2 BHK in Wakad.", "questions_asked": "price?",
                                   "budget_max_inr": 9000000})
    assert e.summary == "Wants a 2 BHK in Wakad." and e.budget_max_inr == 9000000
