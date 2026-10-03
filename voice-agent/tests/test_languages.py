"""Language detection and the switch threshold. Riya speaks Hindi, Marathi and English only."""

from app.lang.languages import LANGS, LanguageTracker, detect_language


def test_scripts_are_recognised():
    assert detect_language("मला दोन बीएचके पाहिजे आहे")[0] == "mr"
    assert detect_language("मुझे दो बीएचके चाहिए")[0] == "hi"
    assert detect_language("I am looking for a two bedroom flat")[0] == "en"


def test_only_three_languages_are_supported():
    assert set(LANGS) == {"hi", "mr", "en"}


def test_gujarati_text_is_not_a_language_riya_switches_to():
    assert detect_language("મને બે બીએચકે જોઈએ છે", "gu-IN") == (None, 0.0)
    tracker = LanguageTracker("hi")
    assert tracker.observe("મને બે બીએચકે જોઈએ છે", "gu-IN") == "hi"
    assert tracker.observe("હા છે જ માં એ જ ભરેલું છે ને આમ.", "gu-IN") == "hi"
    assert tracker.switches == 0


def test_one_english_word_never_flips_the_call():
    tracker = LanguageTracker("hi")
    assert tracker.observe("ok") == "hi"
    assert tracker.observe("hello") == "hi"


def test_the_recogniser_tag_settles_a_switch():
    tracker = LanguageTracker("hi")
    assert tracker.observe("मला दोन बीएचके पाहिजे आहे", "mr-IN") == "mr"
    assert tracker.switches == 1
