"""Chunks follow structure: tables stay whole with their header, FAQ pairs stay together."""

import io

from rag_service.ingest.chunk import ChunkConfig, DocContext, chunk_document, parse_blocks
from rag_service.ingest.files import workbook_pages

CFG = ChunkConfig(target_tokens=120, max_tokens=160, min_tokens=60, table_max_tokens=200, table_row_min_rows=6)


def _table(rows: int) -> str:
    lines = ["| Charge | Amount | Applies to |", "|---|---|---|"]
    lines += [f"| Charge number {i} | ₹{i * 1000} per sq ft | Floors {i} and above |" for i in range(1, rows + 1)]
    return "\n".join(lines)


def test_a_table_is_never_split_and_always_has_its_header():
    md = "# Price sheet\n\nIntro paragraph about charges.\n\n" + _table(40) + "\n\nClosing note."
    chunks = chunk_document([(3, md)], DocContext("PRICE_SHEET", "Sahyadri Grove", "Baner"), CFG)
    tables = [c for c in chunks if c.chunk_type == "TABLE"]
    assert len(tables) > 1, "a 40-row table over budget should be several table chunks"
    seen_rows = []
    for chunk in tables:
        lines = chunk.content.splitlines()
        assert lines[0] == "| Charge | Amount | Applies to |"
        assert lines[1].startswith("|---")
        for row in lines[2:]:
            assert row.startswith("| Charge number") and row.endswith("|"), "a row was cut"
            seen_rows.append(row)
    assert len(seen_rows) == 40 and len(set(seen_rows)) == 40, "every row exactly once across table chunks"


def test_long_tables_also_emit_one_chunk_per_row():
    chunks = chunk_document([(1, "## Charges\n\n" + _table(8))], DocContext("PRICE_SHEET"), CFG)
    rows = [c for c in chunks if c.chunk_type == "TABLE_ROW"]
    assert len(rows) == 8
    assert rows[2].content == "Charge: Charge number 3; Amount: ₹3000 per sq ft; Applies to: Floors 3 and above"
    short = chunk_document([(1, _table(3))], DocContext("PRICE_SHEET"), CFG)
    assert not [c for c in short if c.chunk_type == "TABLE_ROW"]


def test_each_faq_pair_is_exactly_one_chunk():
    md = """# FAQs

## Is there a clubhouse?
Yes, a 12,000 sq ft clubhouse with a gym and indoor games.

## What is the possession date?
Possession of Tower A is planned for December 2027.

Q: Is parking included?
A: One covered parking slot is included with every 2 BHK.
"""
    chunks = chunk_document([(1, md)], DocContext("FAQ", "Sahyadri Grove", "Baner"), CFG)
    faqs = [c for c in chunks if c.chunk_type == "FAQ"]
    assert [c.content.splitlines()[0] for c in faqs] == [
        "Q: Is there a clubhouse?", "Q: What is the possession date?", "Q: Is parking included?"]
    assert "December 2027" in faqs[1].content and "clubhouse" not in faqs[1].content
    assert faqs[2].content.endswith("One covered parking slot is included with every 2 BHK.")


def test_context_header_names_project_type_section_and_page():
    md = "# Amenities\n\n## Clubhouse\n\nA rooftop clubhouse with a pool."
    chunk = chunk_document([(4, md)], DocContext("BROCHURE", "Sahyadri Grove", "Baner, Pune"), CFG)[0]
    assert chunk.context_header == ("Project: Sahyadri Grove (Baner, Pune) · Brochure · "
                                    "Section: Amenities > Clubhouse · Page 4")
    assert chunk.embedding_text.startswith(chunk.context_header)


def test_small_sections_are_packed_and_long_ones_split_with_overlap():
    small = "\n\n".join(f"## Amenity {i}\n\nShort description of amenity {i}." for i in range(5))
    packed = chunk_document([(1, "# Amenities\n\n" + small)], DocContext("BROCHURE"), CFG)
    assert len(packed) == 1 and packed[0].section_path == "Amenities"
    sentences = " ".join(f"Sentence {i} describes the location in some detail for buyers." for i in range(60))
    long = chunk_document([(1, "# Location\n\n" + sentences)], DocContext("BROCHURE"), CFG)
    assert len(long) >= 3
    assert all(c.token_count <= CFG.max_tokens + 20 for c in long)
    tail = long[0].content.split(". ")[-1].strip(". ")
    assert tail.split()[0] in long[1].content, "consecutive chunks of one section overlap"


def test_devanagari_and_gujarati_keep_their_script_and_language():
    chunks = chunk_document([(1, "## सुविधा\n\nप्रोजेक्टमध्ये क्लबहाऊस आणि जिम आहे.\n\n"),
                             (2, "## સુવિધાઓ\n\nપ્રોજેક્ટમાં ક્લબહાઉસ અને જિમ છે.")],
                            DocContext("BROCHURE"), ChunkConfig(min_tokens=1, target_tokens=40, max_tokens=60))
    assert {c.language for c in chunks} == {"mr", "gu"}
    assert any("क्लबहाऊस" in c.content for c in chunks)


def test_spreadsheet_rows_become_row_chunks():
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Charges"
    sheet.append(["Charge", "Amount", "Notes"])
    for name, amount in [("Floor rise", "₹50 per sq ft per floor above 5"), ("PLC garden facing", "₹150 per sq ft"),
                         ("Covered parking", "₹4,00,000"), ("Club membership", "₹2,50,000"),
                         ("Maintenance deposit", "24 months at ₹4 per sq ft"), ("Legal charges", "₹25,000"),
                         ("GST", "5% on agreement value")]:
        sheet.append([name, amount, ""])
    buffer = io.BytesIO()
    book.save(buffer)
    pages = workbook_pages("xlsx", buffer.getvalue())
    chunks = chunk_document([(i + 1, p) for i, p in enumerate(pages)], DocContext("PRICE_SHEET", paged=False), CFG)
    rows = [c for c in chunks if c.chunk_type == "TABLE_ROW"]
    assert "Charge: Floor rise; Amount: ₹50 per sq ft per floor above 5" in [r.content for r in rows]
    assert all("Page" not in c.context_header for c in chunks)
    assert rows[0].section_path == "Charges"


def test_parse_blocks_recognises_markdown_structure():
    blocks = parse_blocks([(1, "# Title\n\n- one\n- two\n\n" + _table(2) + "\n\nWhat is RERA?\nIt is a registration.")])
    assert [b.kind for b in blocks] == ["heading", "text", "table", "question"]
