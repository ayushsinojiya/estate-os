import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { Files } from "../src/pages/Files";
import { queryClient } from "../src/services/query";
import { configureApi } from "../src/api/client";

const auth = vi.hoisted(() => ({ workspaceId: "7", canManage: true }));
vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => auth }));
const id = "799c7ce2-6723-462c-8e50-06f80275667c";
const source = { id, fileName: "brochure.pdf", sizeBytes: 1024, status: "PUBLISHED", docType: "BROCHURE", version: 1, pageCount: 2, chunkCount: 9, costUsd: 0, lowConfidencePageCount: 0 };
let fetchMock: ReturnType<typeof vi.fn>;
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
const page = (items: unknown[]) => ({ items, page: 0, size: 20, total: items.length });
const mount = () => render(<QueryClientProvider client={queryClient}><Files/></QueryClientProvider>);

beforeEach(() => {
  auth.canManage = true;
  auth.workspaceId = "7";
  queryClient.clear();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  configureApi("crm-token", "7");
  fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes("/knowledge/sources?")) return json(page([source]));
    if (url.endsWith("/knowledge/imports")) return json({ items: [{ sourceId: id, status: "IMPORTED", projects: 2, units: 14 }] });
    if (url.includes("/files?")) return json(page([{ id: "12", originalFileName: "legacy.zip", fileSizeBytes: 1024, status: "STORED" }]));
    if (url.endsWith(`/knowledge/sources/${id}`) && !options?.method) return json({ ...source, versions: [{ version: 1, status: "PUBLISHED", createdAt: "2026-10-01T10:00:00Z" }], pages: [{ page: 1, provider: "openai:gpt-4o-mini", confidence: 0.95 }, { page: 2, provider: "pdf-text-layer", confidence: 0.5 }], lowConfidencePages: [2], warnings: ["1 page(s) were parsed with low confidence; check pages [2]"] });
    if (url.endsWith("/batches") || url.endsWith("/replace")) return json({ batchId: "batch-1", results: [{ id, filename: "new.csv", status: "UPLOADED" }] });
    return json({ ...source, status: "UPLOADED" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

describe("knowledge sources", () => {
  it("uses the knowledge service status contract and shows the live version", async () => {
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText("v1 · live")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Filter by status" }));
    await user.click(screen.getByRole("option", { name: "Published" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.includes("status=PUBLISHED"))).toBe(true));
  });

  it("flags sources with low-confidence pages", async () => {
    fetchMock.mockImplementation(async () => json(page([{ ...source, lowConfidencePageCount: 1 }])));
    mount();
    expect(await screen.findByText("Check Pages")).toBeInTheDocument();
  });
  it("uploads a batch immediately from the single upload entrypoint and preserves per-file results", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText("brochure.pdf");
    expect(screen.getAllByRole("button", { name: "Upload files" })).toHaveLength(1);
    await user.upload(screen.getByLabelText("Choose files"), [new File(["name,bhk\nHome,3"], "new.csv", { type: "text/csv" })]);
    expect(await screen.findByText("Batch batch-1")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => url.endsWith("/knowledge/batches"));
    expect(call?.[1]?.body).toBeInstanceOf(FormData);
    expect((call?.[1]?.body as FormData).getAll("files")).toHaveLength(1);
    expect(call?.[1]?.headers).toMatchObject({ Authorization: "Bearer crm-token", "X-Workspace-Id": "7" });
    expect(fetchMock.mock.calls.some(([url, options]) => url.endsWith("/files") && options?.method === "POST")).toBe(false);
  });

  it("replaces using stable source identity even with a different filename", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "Replace brochure.pdf" }));
    await user.upload(screen.getByLabelText("Choose replacement file"), new File(["name,bhk\nHome,4"], "renamed.csv", { type: "text/csv" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/v1/knowledge/sources/${id}/replace`, expect.objectContaining({ method: "POST" })));
    expect(await screen.findByText("Batch batch-1")).toBeInTheDocument();
  });

  it("hides mutation controls for agents but permits viewing history", async () => {
    auth.canManage = false;
    const user = userEvent.setup();
    mount();
    await screen.findByText("brochure.pdf");
    expect(screen.queryByRole("button", { name: "Upload files" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replace brochure.pdf" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete brochure.pdf" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View history for brochure.pdf" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Versions")).toBeInTheDocument();
    expect(within(dialog).getByText("p2 · 50%")).toBeInTheDocument();
    expect(within(dialog).getByText(/low confidence/)).toBeInTheDocument();
  });

  it("retries failed ingestion and confirms deletion before queueing it", async () => {
    fetchMock.mockImplementation(async (url: string) => url.includes("/knowledge/sources?") ? json(page([{ ...source, status: "FAILED", error: "Embedding unavailable" }])) : json({ ...source, status: "UPLOADED" }));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "Retry brochure.pdf" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/v1/knowledge/sources/${id}/retry`, expect.objectContaining({ method: "POST" })));
    await user.click(screen.getByRole("button", { name: "Delete brochure.pdf" }));
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(false);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete source" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/v1/knowledge/sources/${id}`, expect.objectContaining({ method: "DELETE" })));
  });

  it("keeps legacy storage history accessible without treating it as published knowledge", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "Legacy stored files" }));
    expect(await screen.findByText("legacy.zip")).toBeInTheDocument();
    expect(screen.getByText(/not been automatically ingested/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete legacy.zip" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete file" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/files/12", expect.objectContaining({ method: "DELETE" })));
  });

  it("shows service configuration errors and retains access to legacy history", async () => {
    const original = fetchMock.getMockImplementation() as (url: string, options?: RequestInit) => Promise<Response>;
    fetchMock.mockImplementation(async (url: string, options?: RequestInit) => url.includes("/knowledge/") ? json({ message: "Set RAG_SERVICE_TOKEN" }, 503) : original(url, options));
    const user = userEvent.setup();
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Set RAG_SERVICE_TOKEN");
    await user.click(screen.getByRole("button", { name: "Legacy stored files" }));
    expect(await screen.findByText("legacy.zip")).toBeInTheDocument();
  });

  it("polls a queued source until completion then stops", async () => {
    let reads = 0;
    fetchMock.mockImplementation(async (url: string) => url.includes("/knowledge/sources?")
      ? json(page([{ ...source, status: ++reads === 1 ? "PARSING" : "PUBLISHED" }]))
      : json({ items: [] }));
    mount();
    expect(await within(await screen.findByRole("table")).findByText("Parsing")).toBeInTheDocument();
    await waitFor(() => expect(reads).toBe(2), { timeout: 3500 });
    await waitFor(() => expect(within(screen.getByRole("table")).queryByText("Parsing")).not.toBeInTheDocument());
    const completedReads = reads;
    await new Promise((resolve) => setTimeout(resolve, 2300));
    expect(reads).toBe(completedReads);
  }, 7000);
});
