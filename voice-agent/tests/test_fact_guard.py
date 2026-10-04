"""Areas, like prices, may only be spoken when a tool returned them in this call."""

from app.domain.real_estate.guardrails import PriceGuard

INVENTED = ("Skyline Crest में 3 BHK का carpet area 1650 sq ft से 1850 sq ft और built-up area "
            "1880 sq ft से 2100 sq ft है।")


def test_invented_areas_are_caught():
    guard = PriceGuard()
    guard.add_result({"chunks": [{"content": "| 3 BHK | 950 | 2 | 4 |"}]})
    assert guard.unsupported(INVENTED) == [1650, 1850, 1880, 2100]


def test_areas_from_a_tool_result_may_be_spoken():
    guard = PriceGuard()
    guard.add_result({"unitTypes": [{"bhk": 3, "carpetAreaSqft": 950}]})
    assert guard.unsupported("Skyline Crest में 3 BHK का carpet area 950 sq ft है।") == []
    assert guard.unsupported("3 BHK carpet area ९५० वर्ग फुट है") == []


def test_sentences_without_an_area_are_not_affected():
    guard = PriceGuard()
    assert guard.unsupported("Visit Sunday 10 AM, Tower A, floor 12.") == []


def test_prices_are_still_checked():
    guard = PriceGuard()
    guard.add_result({"priceMinInr": 7650000})
    assert guard.unsupported("2 BHK 76.5 lakh से शुरू है") == []
    assert guard.unsupported("2 BHK 60 lakh में है") == [6000000]
