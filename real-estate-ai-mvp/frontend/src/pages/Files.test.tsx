import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { Files } from "./Files";
import { queryClient } from "../services/query";
import { configureApi } from "../api/client";

const auth = vi.hoisted(() => ({ workspaceId: "7", canManage: true }));
vi.mock("../hooks/useAuth", () => ({ useAuth: () => auth }));
const id = "799c7ce2-6723-462c-8e50-06f80275667c";
const source = { id, originalFileName: "brochure.pdf", fileSizeBytes: 1024, status: "ACTIVE", stage: "COMPLETE", version: 1, activeVersion: "f09f2e57-ed02-4da8-a518-01ebc3d572bf", activeVersionNumber: 1 };
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
    if (url.includes("/files?")) return json(page([{ ...source, id: "12", originalFileName: "legacy.zip", status: "STORED" }]));
    if (url.endsWith(`/knowledge/sources/${id}`) && !options?.method) return json({ source, versions: [{ id: "v1", version: 1, status: "ACTIVE" }], jobs: [], logs: [{ id: "l1", stage: "PUBLISH", message: "Published grounded facts" }], events: [{ id: "a1", action: "UPLOAD", user_id: "42" }] });
    if (url.endsWith("/batches") || url.endsWith("/replace")) return json({ batchId: "batch-1", results: [{ id, filename: "new.csv", status: "QUEUED" }] });
    return json({ jobId: "job-1", status: "QUEUED" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

describe("knowledge sources", () => {
  it("uses the live status contract and displays the version number instead of its UUID", async () => {
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText("v1 · live v1")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Filter by status" }));
    await user.click(screen.getByRole("option", { name: "Active" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.includes("status=ACTIVE"))).toBe(true));
  });

  it("does not offer Retry for a permanent parser rejection", async () => {
    fetchMock.mockImplementation(async () => json(page([{ ...source, status: "FAILED", retryable: false }])));
    mount();
    await screen.findByText("brochure.pdf");
    expect(screen.queryByRole("button", {name: "Retry brochure.pdf"})).not.toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Replace brochure.pdf"})).toBeEnabled();
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
    expect(await within(dialog).findByText("Processing logs")).toBeInTheDocument();
    expect(within(dialog).getByText("Audit activity")).toBeInTheDocument();
  });

  it("retries failed ingestion and confirms deletion before queueing it", async () => {
    fetchMock.mockImplementation(async (url: string) => url.includes("/knowledge/sources?") ? json(page([{ ...source, status: "FAILED", stage: "EMBEDDING", failureReason: "Embedding unavailable" }])) : json({ jobId: "job-1", status: "QUEUED" }));
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
    fetchMock.mockImplementation(async (url: string, options?: RequestInit) => url.includes("/knowledge/") ? json({ message: "Set RAG_INGESTION_TOKEN" }, 503) : original(url, options));
    const user = userEvent.setup();
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Set RAG_INGESTION_TOKEN");
    await user.click(screen.getByRole("button", { name: "Legacy stored files" }));
    expect(await screen.findByText("legacy.zip")).toBeInTheDocument();
  });

  it("polls a queued source until completion then stops", async () => {
    let reads = 0;
    fetchMock.mockImplementation(async () => json(page([{ ...source, status: ++reads === 1 ? "QUEUED" : "COMPLETED" }])));
    mount();
    expect(await within(await screen.findByRole("table")).findByText("Queued")).toBeInTheDocument();
    await waitFor(() => expect(reads).toBe(2), { timeout: 3500 });
    await waitFor(() => expect(within(screen.getByRole("table")).queryByText("Queued")).not.toBeInTheDocument());
    const completedReads = reads;
    await new Promise((resolve) => setTimeout(resolve, 2300));
    expect(reads).toBe(completedReads);
  }, 7000);
});
