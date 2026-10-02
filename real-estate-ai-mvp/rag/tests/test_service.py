"""The service against a real pgvector database: tenancy, publication, versions and contracts."""

import asyncio
import uuid

from tests.conftest import CRM, VOICE, drain, upload, voice

BROCHURE_A = """# Sahyadri Grove

## Amenities

### Clubhouse
A 12,000 sq ft clubhouse with a rooftop infinity pool, gym and indoor games room.

### Kids
A children's play area and a skating rink near Tower B.

## Location
Ten minutes from Baner high street and the Mumbai–Bengaluru highway.
"""

BROCHURE_B = """# Northstar Meadows

## Amenities
A private clubhouse with a squash court and a rooftop infinity pool.
"""


async def _publish(client, services, ws, name, text, **form):
    result = await upload(client, ws, name, text.encode(), **form)
    await drain(services)
    return result


async def test_ingest_publishes_and_retrieval_cites_the_chunk(client, services):
    created = await _publish(client, services, 1, "sahyadri-brochure.md", BROCHURE_A, projectId=11,
                             projectName="Sahyadri Grove", locality="Baner", crmDocumentId=501)
    detail = (await client.get(f"/v1/workspaces/1/sources/{created['id']}", headers=CRM)).json()
    assert detail["status"] == "PUBLISHED" and detail["chunkCount"] >= 1
    assert detail["docType"] == "BROCHURE"
    body = (await voice(client, 1, "rooftop infinity pool clubhouse", projectId=11)).json()
    assert body["inventoryAuthoritative"] == "crm"
    top = body["results"][0]
    assert top["documentId"] == "501" and "infinity pool" in top["content"]
    assert top["sectionPath"].startswith("Sahyadri Grove")  # small sections are packed under their parent


async def test_a_workspace_never_sees_another_workspaces_chunks(client, services):
    await _publish(client, services, 1, "a.md", BROCHURE_A)
    await _publish(client, services, 2, "b.md", BROCHURE_B)
    for ws, other in ((1, "Northstar"), (2, "Sahyadri")):
        response = await client.post("/v1/voice/retrieve", headers=CRM,
                                     json={"workspaceId": ws, "query": "rooftop infinity pool clubhouse", "k": 10})
        contents = " ".join(r["content"] + r["title"] for r in response.json()["results"])
        assert response.json()["results"], f"workspace {ws} found nothing of its own"
        assert other not in contents, f"workspace {ws} saw another workspace's document"
    # Every lower layer is scoped too: listing and detail.
    listed = (await client.get("/v1/workspaces/2/sources", headers=CRM)).json()
    assert [i["title"] for i in listed["items"]] == ["b"]
    other_id = (await client.get("/v1/workspaces/1/sources", headers=CRM)).json()["items"][0]["id"]
    assert (await client.get(f"/v1/workspaces/2/sources/{other_id}", headers=CRM)).status_code == 404


async def test_the_voice_token_is_bound_to_its_workspace(client, services):
    await _publish(client, services, 1, "a.md", BROCHURE_A)
    assert (await voice(client, 1, "clubhouse")).status_code == 200
    assert (await voice(client, 2, "clubhouse")).status_code == 403
    assert (await voice(client, 1, "clubhouse", headers={"Authorization": "Bearer nope"})).status_code == 401
    # The voice token is not a CRM token.
    assert (await client.get("/v1/workspaces/1/sources", headers=VOICE)).status_code == 401


async def test_unpublished_and_deleted_documents_are_never_returned(client, services):
    a = await _publish(client, services, 1, "a.md", BROCHURE_A)
    assert (await voice(client, 1, "skating rink")).json()["results"]
    unpublished = await client.post(f"/v1/workspaces/1/sources/{a['id']}/unpublish", headers=CRM)
    assert unpublished.json()["status"] == "UNPUBLISHED"
    assert (await voice(client, 1, "skating rink")).json()["results"] == []
    republished = await client.post(f"/v1/workspaces/1/sources/{a['id']}/publish", headers=CRM)
    assert republished.json()["status"] == "PUBLISHED"
    assert (await voice(client, 1, "skating rink")).json()["results"]
    deleted = await client.delete(f"/v1/workspaces/1/sources/{a['id']}", headers=CRM)
    assert deleted.status_code == 202
    assert (await voice(client, 1, "skating rink")).json()["results"] == []
    async with services.db.conn() as conn:
        assert (await (await conn.execute("SELECT count(*) AS n FROM kb_chunks")).fetchone())["n"] == 0
    assert (await client.get(f"/v1/workspaces/1/sources/{a['id']}", headers=CRM)).status_code == 404


async def test_a_document_still_processing_is_not_searchable(client, services):
    await upload(client, 1, "a.md", BROCHURE_A.encode())
    assert (await voice(client, 1, "skating rink")).json()["results"] == []
    await drain(services)
    assert (await voice(client, 1, "skating rink")).json()["results"]


async def test_duplicate_bytes_are_detected_per_workspace(client, services):
    first = await _publish(client, services, 1, "a.md", BROCHURE_A)
    again = await upload(client, 1, "copy-of-a.md", BROCHURE_A.encode())
    assert again["status"] == "DUPLICATE" and again["id"] == first["id"]
    elsewhere = await upload(client, 2, "a.md", BROCHURE_A.encode())
    assert elsewhere["status"] == "UPLOADED", "another workspace may hold the same file"


async def test_replacing_swaps_versions_atomically(client, services):
    old = await _publish(client, services, 1, "plan.md", "# Payment plan\n\nBooking amount is 10 percent.")
    replaced = await client.post(f"/v1/workspaces/1/sources/{old['id']}/replace", headers=CRM,
                                 files=[("files", ("plan-v2.md", b"# Payment plan\n\nBooking amount is 12 percent."))])
    assert replaced.status_code == 202 and replaced.json()["results"][0]["version"] == 2

    observed = []

    async def watch():
        for _ in range(60):
            results = (await voice(client, 1, "booking amount percent", k=10)).json()["results"]
            text = " ".join(r["content"] for r in results)
            observed.append(("10 percent" in text, "12 percent" in text))
            await asyncio.sleep(0)

    await asyncio.gather(watch(), drain(services))
    # Before the swap only v1, after it only v2; never both and never neither.
    assert all(old_seen != new_seen for old_seen, new_seen in observed), observed
    final = (await voice(client, 1, "booking amount percent", k=10)).json()["results"]
    assert all("12 percent" in r["content"] for r in final)
    detail = (await client.get(f"/v1/workspaces/1/sources/{old['id']}", headers=CRM)).json()
    assert detail["version"] == 2 and [v["status"] for v in detail["versions"]] == ["PUBLISHED", "SUPERSEDED"]


async def test_crm_document_contract(client, services):
    ws, project, doc = "1", "11", "777"
    base = {"workspaceId": ws, "projectId": project, "documentId": doc, "language": "en"}
    status = (await client.post("/v1/documents/status", headers=CRM, json=base)).json()
    assert status["status"] == "NOT_INDEXED" and status["documentId"] == doc
    indexed = (await client.post("/v1/content/index", headers=CRM, json={
        **base, "content": "# FAQ\n\n## Is there a gym?\nYes, on the second floor of the clubhouse.",
        "title": "FAQ", "status": "PUBLISHED", "publishedOnly": True})).json()
    assert indexed["documentId"] == doc and indexed["status"] == "UPLOADED"
    await drain(services)
    status = (await client.post("/v1/documents/status", headers=CRM, json=base)).json()
    assert status["status"] == "PUBLISHED" and status["searchable"] is True
    search = (await client.post("/v1/knowledge/search", headers=CRM, json={
        **base, "query": "gym", "publishedOnly": True, "status": "PUBLISHED",
        "publishedDocumentIds": [doc], "leadId": None, "budgetMin": None})).json()
    assert search["results"] and search["results"][0]["documentId"] == doc
    assert search["results"][0]["status"] == "PUBLISHED" and search["results"][0]["workspaceId"] == ws
    # The allowlist is honoured: an empty list or another id returns nothing.
    for allow in ([], ["999"]):
        none = (await client.post("/v1/knowledge/search", headers=CRM, json={
            **base, "query": "gym", "publishedDocumentIds": allow})).json()
        assert none["results"] == []
    unpublished = (await client.post("/v1/content/unpublish", headers=CRM, json=base)).json()
    assert unpublished["status"] == "UNPUBLISHED"
    assert (await voice(client, 1, "gym second floor")).json()["results"] == []
    reindexed = (await client.post("/v1/documents/reindex", headers=CRM, json=base)).json()
    assert reindexed["status"] == "UPLOADED"
    await drain(services)
    assert (await voice(client, 1, "gym second floor")).json()["results"]


async def test_jobs_are_claimed_once_across_workers(client, services):
    for i in range(6):
        await upload(client, 1, f"doc{i}.md", f"# Doc {i}\n\nUnique text number {i} {uuid.uuid4()}".encode())
    claimed = await asyncio.gather(*(services.store.claim_job(f"w{i}") for i in range(6)))
    ids = [job["id"] for job in claimed if job]
    assert len(ids) == len(set(ids)) == 6


async def test_a_failing_job_backs_off_and_then_fails_the_document(client, services, monkeypatch):
    from rag_service.ingest import pipeline

    async def broken(*args, **kwargs):
        raise RuntimeError("provider outage")

    monkeypatch.setattr("rag_service.worker.ingest", broken)
    created = await upload(client, 1, "a.md", BROCHURE_A.encode())
    async with services.db.conn() as conn:
        await conn.execute("UPDATE kb_jobs SET max_attempts=2")
    await drain(services)
    await asyncio.sleep(0.05)
    await drain(services)
    detail = (await client.get(f"/v1/workspaces/1/sources/{created['id']}", headers=CRM)).json()
    assert detail["status"] == "FAILED" and "provider outage" in detail["error"]
    retried = await client.post(f"/v1/workspaces/1/sources/{created['id']}/retry", headers=CRM)
    assert retried.status_code == 202 and retried.json()["status"] == "UPLOADED"
    assert pipeline.ingest is not broken


async def test_rejected_uploads(client, services):
    response = await client.post("/v1/workspaces/1/sources", headers=CRM,
                                 files=[("files", ("x.pdf", b"not a pdf")), ("files", ("y.exe", b"MZ"))])
    assert [r["status"] for r in response.json()["results"]] == ["REJECTED", "REJECTED"]
    assert (await client.get("/v1/workspaces/1/sources", headers={"Authorization": "Bearer x"})).status_code == 401


async def test_pdf_text_layer_ingests_offline_and_low_confidence_pages_are_flagged(client, services):
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, "Sahyadri Grove RERA registration P52100012345")
    pdf.showPage()
    pdf.showPage()  # an empty page: nothing to parse
    pdf.save()
    created = await upload(client, 1, "rera.pdf", buffer.getvalue(), projectId=11)
    await drain(services)
    detail = (await client.get(f"/v1/workspaces/1/sources/{created['id']}", headers=CRM)).json()
    assert detail["status"] == "PUBLISHED" and detail["docType"] == "RERA"
    assert detail["lowConfidencePages"] == [2] and detail["warnings"]
    hit = (await voice(client, 1, "P52100012345")).json()["results"][0]
    assert "P52100012345" in hit["content"] and hit["page"] == 1


async def test_publishing_an_already_indexed_file_does_not_parse_it_again(client, services):
    """CRM upload sends the file; the publish click that follows must not pay for a second parse."""
    created = await _publish(client, services, 1, "grove-brochure.md", BROCHURE_A, projectId=11, crmDocumentId=601)
    base = {"workspaceId": "1", "projectId": "11", "documentId": "601", "status": "PUBLISHED", "publishedOnly": True}
    for _ in range(2):
        status = (await client.post("/v1/content/index", headers=CRM, json=base)).json()
        assert status["status"] == "PUBLISHED"
    detail = (await client.get(f"/v1/workspaces/1/sources/{created['id']}", headers=CRM)).json()
    assert [v["version"] for v in detail["versions"]] == [1]
    # An unpublished file comes back without a re-parse; an explicit reindex still re-parses.
    await client.post("/v1/content/unpublish", headers=CRM, json=base)
    assert (await client.post("/v1/content/index", headers=CRM, json=base)).json()["status"] == "PUBLISHED"
    assert (await voice(client, 1, "rooftop infinity pool")).json()["results"]
    assert (await client.post("/v1/documents/reindex", headers=CRM, json=base)).json()["status"] == "UPLOADED"
