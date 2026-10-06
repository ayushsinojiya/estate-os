"""Projects and listings read from documents for the CRM's Projects & inventory."""

from __future__ import annotations

import pytest

from rag_service.extract import extract, map_columns, parse_area, parse_bhk, parse_price, usable
from tests.conftest import CRM, drain, upload

CSV = (b"property_id,transaction,locality,property_type,configuration,carpet_or_plot_sqft,price,amenities\n"
       b"PUN-0001,Rent,Aundh,1 RK Apartment,1 RK,443,\"\xe2\x82\xb922,147/month\",\"Lift, CCTV\"\n"
       b"PUN-0003,Buy,Aundh,2 BHK Apartment,2 BHK,829,\xe2\x82\xb979.2 lakh,Clubhouse\n"
       b"PUN-0004,Buy,Baner,3 BHK Apartment,3 BHK,1194,\xe2\x82\xb91.05 crore,\n")


def test_prices_areas_and_bedrooms_are_parsed_exactly():
    assert parse_price("₹79.2 lakh") == (7_920_000, False)
    assert parse_price("■1.05 crore") == (10_500_000, False)
    assert parse_price("₹22,147/month") == (22_147, True)
    assert parse_price("Rs. 45 Lac") == (4_500_000, False)
    assert parse_price("on request") == (None, False)
    assert parse_area("829 sq ft") == 829 and parse_area("2 acres") == 87_120
    assert parse_bhk("2 BHK Type A") == 2 and parse_bhk("1 RK") == 0 and parse_bhk("Warehouse") == 0


def test_listing_columns_are_found_by_name():
    header = ["property_id", "transaction", "locality", "property_type", "configuration",
              "carpet_or_plot_sqft", "price", "furnishing", "notes"]
    mapping = map_columns(header)
    assert usable(mapping)
    assert [header[mapping[f]] for f in ("ref", "transaction", "area", "price", "propertyType", "configuration")] == \
        ["property_id", "transaction", "carpet_or_plot_sqft", "price", "property_type", "configuration"]


class FakeModel:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    async def complete(self, system, user):
        self.calls += 1
        return self.reply


async def test_a_price_the_model_did_not_copy_from_the_page_is_dropped():
    page = ("# Shivalik Sky - Project Brochure\nDeveloper: Shivalik Developers, South Bopal\n"
            "| BHK | Starting Price |\n|---|---|\n| 2 BHK | ₹72 lakh |\n")
    model = FakeModel({"projects": [{"name": "Shivalik Sky", "developer": "Shivalik", "location": "South Bopal, Ahmedabad"}],
                       "listings": [{"projectName": "Shivalik Sky", "configuration": "2 BHK", "price": "₹72 lakh"},
                                    {"projectName": "Shivalik Sky", "configuration": "3 BHK", "price": "₹95 lakh"}]})
    result = await extract([(1, page)], "brochure.pdf", model)
    assert [(l["configuration"], l["priceInr"], l["transaction"], l["projectName"]) for l in result["listings"]] == \
        [("2 BHK", 7_200_000, "SALE", "Shivalik Sky")], "the table is read in code and given the page's project"
    assert result["projects"][0]["city"] == "Ahmedabad"
    assert "not on the page" in result["warnings"][0]


async def test_pages_without_prices_are_not_sent_to_the_model():
    model = FakeModel({"projects": [], "listings": []})
    await extract([(1, "## Aundh\nAundh is a quiet locality with good schools.")], "guide.docx", model)
    assert model.calls == 0


async def test_a_big_listing_table_is_read_in_code_without_the_model():
    rows = "\n".join(f"| PUN-{i:04d} | Buy | Wakad | 2 BHK Apartment | 2 BHK | 900 | ₹{60 + i} lakh |" for i in range(40))
    page = "| property_id | transaction | locality | property_type | configuration | carpet_or_plot_sqft | price |\n|---|---|---|---|---|---|---|\n" + rows
    model = FakeModel({"projects": [], "listings": []})
    result = await extract([(1, page)], "pune_master_inventory.csv", model)
    assert len(result["listings"]) == 40 and model.calls == 0
    assert result["listings"][0]["priceInr"] == 6_000_000 and result["city"] == "Pune"


async def test_extraction_runs_after_publishing_and_is_served_to_the_crm(client, services):
    created = await upload(client, 1, "pune_master_inventory.csv", CSV)
    await drain(services)
    response = await client.get(f"/v1/workspaces/1/sources/{created['id']}/extraction", headers=CRM)
    body = response.json()
    assert body["status"] == "DONE", body
    listings = {l["ref"]: l for l in body["extraction"]["listings"]}
    assert listings["PUN-0001"]["transaction"] == "RENT" and listings["PUN-0001"]["priceInr"] == 22_147
    assert listings["PUN-0004"]["priceInr"] == 10_500_000 and listings["PUN-0004"]["locality"] == "Baner"
    assert listings["PUN-0001"]["amenities"] == ["Lift", "CCTV"]


async def test_a_source_published_before_extraction_existed_is_queued_on_request(client, services):
    created = await upload(client, 1, "inventory.csv", CSV)
    await drain(services)
    async with services.db.conn() as conn:
        await conn.execute("UPDATE kb_documents SET extraction=NULL, extraction_status='NONE'")
    first = (await client.get(f"/v1/workspaces/1/sources/{created['id']}/extraction", headers=CRM)).json()
    assert first["status"] == "QUEUED"
    await drain(services)
    again = (await client.get(f"/v1/workspaces/1/sources/{created['id']}/extraction", headers=CRM)).json()
    assert again["status"] == "DONE" and len(again["extraction"]["listings"]) == 3


async def test_a_retry_rereads_a_file_read_before_the_model_was_configured(client, services):
    created = await upload(client, 1, "inventory.csv", CSV)
    await drain(services)
    url = f"/v1/workspaces/1/sources/{created['id']}/extraction"
    assert (await client.get(url, headers=CRM)).json()["status"] == "DONE"
    services.extraction_model = FakeModel({"projects": [], "listings": []})
    assert (await client.get(url, headers=CRM)).json()["status"] == "DONE", "only a retry re-reads"
    assert (await client.get(url + "?retry=true", headers=CRM)).json()["status"] == "QUEUED"
    await drain(services)
    again = (await client.get(url, headers=CRM)).json()
    assert again["status"] == "DONE" and again["extraction"]["model"] == "fake"
    assert len(again["extraction"]["listings"]) == 3


async def test_a_listing_code_is_never_taken_for_a_project():
    page = "## PUN-0004 - Buy - 3 BHK Apartment - Aundh\n| Price | ₹144.1 lakh | Area | 1194 sq ft |\n|---|---|---|---|\n"
    model = FakeModel({"projects": [{"name": "PUN-0004", "location": "Aundh"}],
                       "listings": [{"ref": "PUN-0004", "projectName": "PUN-0004", "price": "₹144.1 lakh",
                                     "area": "1194 sq ft", "locality": "Aundh", "configuration": "3 BHK"}]})
    result = await extract([(1, page)], "inventory_pack_01.pdf", model)
    assert result["projects"] == []
    assert result["listings"][0]["projectName"] is None and result["listings"][0]["locality"] == "Aundh"
