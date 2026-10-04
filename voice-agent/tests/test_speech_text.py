"""What the caller hears: figures must survive the conversion to Hindi and Marathi speech.

Ported from the bank agent; the figures are now property figures, the conversions are the same.
"""

import pytest

from app.lang.devanagari import to_devanagari_speech


@pytest.mark.parametrize("text,heard", [
    ("मेंटेनेंस ₹2,500 है।", "दो हज़ार पाँच सौ रुपये"),
    ("बुकिंग अमाउंट ₹1,00,000 है।", "एक लाख रुपये"),
    ("कीमत ₹1.5 crore से शुरू।", "डेढ़ करोड़ रुपये"),
    ("इस प्रोजेक्ट का रेरा नंबर P52100012345 है।", "पाँच दो एक शून्य शून्य शून्य एक दो तीन चार पाँच"),
    ("साइट ऑफिस 1800-419-2266 पर।", "एक आठ शून्य शून्य, चार एक नौ, दो दो छह छह"),
    ("पिन 411038 है।", "चार एक एक शून्य तीन आठ"),
    ("डाउन पेमेंट 7.50% है।", "साढ़े सात प्रतिशत"),
    ("सुबह 10 AM से 4 PM तक।", "दस बजे से चार बजे"),
    ("24x7 सिक्योरिटी है।", "चौबीसों घंटे"),
])
def test_hindi_figures_are_spoken_correctly(text, heard):
    assert heard in to_devanagari_speech(text, "hi")


def test_marathi_money_is_spoken_in_marathi():
    assert "दोन हजार पाचशे रुपये" in to_devanagari_speech("मेंटेनन्स ₹2,500 आहे.", "mr")


def test_an_english_sentence_is_left_to_the_tts():
    text = "The 2 BHK starts at 85 lakh for 950 sq ft."
    assert to_devanagari_speech(text, "hi") == text


def test_gujarati_and_english_are_left_to_the_tts():
    text = "બે BHK 85 લાખથી શરૂ થાય છે."
    assert to_devanagari_speech(text, "gu") == text


@pytest.mark.parametrize("text,heard", [
    ("फ्लोर राइज़ ₹50 – ₹100 प्रति sq ft है।", "पचास रुपये से एक सौ रुपये"),
    ("पज़ेशन 7–45 दिन में।", "सात से पैंतालीस दिन"),
])
def test_ranges_are_spoken_as_ranges(text, heard):
    assert heard in to_devanagari_speech(text, "hi")


def test_a_phone_number_is_not_turned_into_a_range():
    assert "एक आठ शून्य शून्य, चार एक नौ, दो दो छह छह" in to_devanagari_speech("कॉल 1800-419-2266 पर।", "hi")


def test_a_project_name_is_spoken_in_devanagari():
    names = {"Baner": "बाणेर"}
    assert "बाणेर" in to_devanagari_speech("Baner में दो BHK है।", "hi", names)
