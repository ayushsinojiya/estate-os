"""Language detection and the switch threshold, including Gujarati."""

from app.lang.languages import LanguageTracker, detect_language
from app.lang import spoken


def test_scripts_are_recognised():
    assert detect_language("मला दोन बीएचके पाहिजे आहे")[0] == "mr"
    assert detect_language("मुझे दो बीएचके चाहिए")[0] == "hi"
    assert detect_language("મને બે બીએચકે જોઈએ છે")[0] == "gu"
    assert detect_language("I am looking for a two bedroom flat")[0] == "en"


def test_codemix_gujarati_in_latin_letters():
    assert detect_language("mane 2 bhk joie che")[0] == "gu"


def test_one_english_word_never_flips_the_call():
    tracker = LanguageTracker("hi")
    assert tracker.observe("ok") == "hi"
    assert tracker.observe("hello") == "hi"


def test_the_recogniser_tag_settles_a_switch():
    tracker = LanguageTracker("hi")
    assert tracker.observe("મને બે બીએચકે જોઈએ છે", "gu-IN") == "gu"
    assert tracker.switches == 1


def test_gujarati_spoken_forms_do_not_fail():
    assert spoken.SCALE["gu"]["crore"] == "કરોડ"
    assert spoken.integer_words(5, "gu") == "5"
    assert "લાખ" in spoken.inr_words(8_500_000, "gu")
