import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileClock, Plus, RefreshCw, Replace, Trash2 } from "../components/icons";
import { api, upload } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useList } from "../hooks/useList";
import { queryClient } from "../services/query";
import type { Entity, Page } from "../types";
import { bytes, date, label } from "../utils/format";
import { dateBounds } from "../utils/dateFilter";
import { Async, Badge, DataTable, ErrorState, Filters, Modal, PageHeader, Pagination, useToast } from "../components/ui";

const supported = ".pdf,.docx,.pptx,.xls,.xlsx,.csv,.txt,.md,.jpg,.jpeg,.png,.webp";
const supportedExtensions = new Set(supported.split(",").map((extension) => extension.slice(1)));
const isWorking = (source: Entity) => ["UPLOADED", "PARSING", "EMBEDDING"].includes(source.status);
type Outcome = { id?: string; filename: string; status: string; reason?: string };
/** What a file added to Projects & inventory (see KnowledgeInventoryImport on the CRM). */
type InventoryImport = { sourceId: string; status: string; projects: number; units: number; message?: string };
type SourceDetails = Entity & {
  versions?: { version: number; status: string; createdAt: string }[];
  pages?: { page: number; provider: string; confidence: number }[];
  lowConfidencePages?: number[];
  warnings?: string[];
};

export function Files() {
  const { workspaceId } = useAuth();
  return <WorkspaceFiles key={workspaceId} />;
}

function WorkspaceFiles() {
  const { workspaceId, canManage } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const replacementInput = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"sources" | "legacy">("sources");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [batchId, setBatchId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [remove, setRemove] = useState<Entity | null>(null);
  const [replace, setReplace] = useState<Entity | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const toast = useToast();
  const bounds = dateBounds(dateFrom, dateTo);
  const path = `/knowledge/sources?page=${page}&size=20&search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}&dateFrom=${encodeURIComponent(bounds.dateFrom)}&dateTo=${encodeURIComponent(bounds.dateTo)}`;
  const query = useQuery<Page>({
    queryKey: [workspaceId, path], queryFn: () => api<Page>(path), enabled: tab === "sources" && !!workspaceId,
    refetchInterval: (result) => result.state.data?.items.some(isWorking) ? 2000 : false,
  });
  const imports = useQuery<{ items: InventoryImport[] }>({
    queryKey: [workspaceId, "/knowledge/imports"], queryFn: () => api("/knowledge/imports"), enabled: tab === "sources" && !!workspaceId,
    refetchInterval: (result) => (Array.isArray(result.state.data?.items) && result.state.data.items.some((i) => i.status === "PENDING")) ? 5000 : false,
  });
  const importBySource = new Map((Array.isArray(imports.data?.items) ? imports.data.items : []).map((i) => [i.sourceId, i]));
  const refresh = () => queryClient.invalidateQueries({ queryKey: [workspaceId] });

  async function syncInventory() {
    setBusy(true); setError(null);
    try {
      await api("/knowledge/imports/sync", { method: "POST" });
      await refresh();
      toast("Projects & inventory are up to date with these files");
    } catch (nextError) { setError(nextError); }
    finally { setBusy(false); }
  }

  async function choose(files: FileList | null, replacing?: Entity) {
    const values = Array.from(files || []);
    if (!values.length || !canManage || busy) return;
    const rejected: Outcome[] = [];
    const accepted = values.filter((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase() || "";
      const reason = file.size > 50 * 1024 * 1024 ? "File exceeds the 50 MB upload limit"
        : !supportedExtensions.has(extension) ? "This file type is not supported for knowledge ingestion"
        : file.size === 0 ? "The file is empty" : "";
      if (reason) rejected.push({ filename: file.name, status: "REJECTED", reason });
      return !reason;
    });
    setOutcomes(rejected); setBatchId(""); setError(null); setTab("sources");
    if (!accepted.length) return;
    setBusy(true);
    try {
      const response = await upload<{ batchId: string; results: Outcome[] }>(
        replacing ? `/knowledge/sources/${replacing.id}/replace` : "/knowledge/batches", accepted,
      );
      setBatchId(response.batchId);
      setOutcomes([...rejected, ...response.results]);
      setPage(0); setSearch(""); setStatus(""); setDateFrom(""); setDateTo("");
      await refresh();
      toast("Upload received; processing results appear below");
    } catch (nextError) { setError(nextError); }
    finally {
      setBusy(false); setReplace(null);
      if (input.current) input.current.value = "";
      if (replacementInput.current) replacementInput.current.value = "";
    }
  }

  async function action(source: Entity, operation: "retry" | "delete") {
    setBusy(true); setError(null);
    try {
      await api(`/knowledge/sources/${source.id}${operation === "retry" ? "/retry" : ""}`, { method: operation === "retry" ? "POST" : "DELETE" });
      await refresh(); setRemove(null);
      toast(operation === "retry" ? "Retry queued" : "Source deleted; it no longer appears in answers");
    } catch (nextError) { setError(nextError); setRemove(null); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader title="File management" description="Upload property sources, follow processing, and manage published knowledge." action={canManage && <button className="btn-primary" disabled={busy} onClick={() => input.current?.click()}><Plus size={17}/> {busy ? "Working…" : "Upload files"}</button>} />
    <input ref={input} className="sr-only" aria-label="Choose files" type="file" multiple accept={supported} disabled={!canManage || busy} onChange={(event) => void choose(event.target.files)} />
    <input ref={replacementInput} className="sr-only" aria-label="Choose replacement file" type="file" accept={supported} disabled={!canManage || busy} onChange={(event) => { if (replace) void choose(event.target.files, replace); }} />
    <div className="flex flex-wrap gap-2 mb-4" aria-label="File views">
      <button className={tab === "sources" ? "btn-primary" : "btn-secondary"} aria-pressed={tab === "sources"} onClick={() => setTab("sources")}>Knowledge sources</button>
      <button className={tab === "legacy" ? "btn-primary" : "btn-secondary"} aria-pressed={tab === "legacy"} onClick={() => setTab("legacy")}>Legacy stored files</button>
    </div>
    {error !== null && <ErrorState error={error} />}
    {tab === "sources" ? <>
      <section className="panel p-5 space-y-3 min-w-0">
        <h2 className="text-lg font-semibold">Property knowledge</h2>
        <p className="text-muted">PDF, Word, PowerPoint, Excel, CSV, text, Markdown and images (JPG, PNG, WEBP). Maximum 50 MB per file. Files are parsed, indexed and published automatically; a replacement goes live only once it is fully indexed. These are workspace-wide sources — documents for one project belong on that project's Documents tab.</p>
        <p className="text-muted">Projects and properties with a price in these files are also added to Projects &amp; inventory, within a few minutes of publishing. Replacing a file updates them; deleting it takes its units off the market.</p>
        {canManage && <button className="btn-secondary" disabled={busy} onClick={() => void syncInventory()}><RefreshCw size={17}/> Sync inventory now</button>}
        {!canManage && <p className="text-muted">An administrator or manager can upload, replace, retry, or delete sources.</p>}
        {busy && <p role="status">Submitting your request…</p>}
        {outcomes.length > 0 && <div className="space-y-2" aria-live="polite">
          <h3 className="font-semibold">Latest upload results</h3>
          {batchId && <p className="text-muted break-all">Batch {batchId}</p>}
          {outcomes.map((item, index) => <div className="flex flex-wrap items-center justify-between gap-3 rounded border p-3" key={`${item.filename}-${index}`}><div className="min-w-0 flex-1"><strong className="break-all">{item.filename}</strong>{item.reason && <p className="text-muted break-words">{item.reason}</p>}</div><Badge value={item.status}/></div>)}
        </div>}
      </section>
      <section className="panel mt-6 min-w-0 max-w-full">
        <Filters search={search} onSearch={(value) => { setSearch(value); setPage(0); }} status={status} onStatus={(value) => { setStatus(value); setPage(0); }} statuses={["UPLOADED", "PARSING", "EMBEDDING", "PUBLISHED", "FAILED", "UNPUBLISHED"]}
          dateFrom={dateFrom} dateTo={dateTo} onDateFrom={(value) => { setDateFrom(value); setPage(0); }} onDateTo={(value) => { setDateTo(value); setPage(0); }} />
        <Async query={query}><DataTable dateFilter={false} data={query.data?.items || []} empty="No knowledge sources match the current filters." columns={[
          { key: "fileName", label: "Source", render: (source) => <button className="text-link text-left whitespace-normal break-all max-w-xs" onClick={() => setDetails(source.id)}>{source.fileName}</button> },
          { key: "sizeBytes", label: "Size", render: (source) => bytes(source.sizeBytes) },
          { key: "status", label: "Status", render: (source) => <><Badge value={source.status}/>{source.lowConfidencePageCount > 0 && <span className="ml-1"><Badge value="CHECK_PAGES"/></span>}{source.error && <p className="text-muted whitespace-normal break-words max-w-xs mt-1">{source.error}</p>}</> },
          { key: "docType", label: "Type", render: (source) => label(source.docType) },
          { key: "inventory", label: "Inventory", render: (source) => {
            if (source.crmDocumentId) return <span className="text-muted">Project document</span>;
            const item = importBySource.get(source.id);
            if (!item) return <span className="text-muted">{source.status === "PUBLISHED" ? "Waiting" : "—"}</span>;
            if (item.status === "IMPORTED") return <span>{item.projects} project{item.projects === 1 ? "" : "s"} · {item.units} unit{item.units === 1 ? "" : "s"}</span>;
            return <span className="whitespace-normal break-words max-w-xs inline-block"><Badge value={item.status}/>{item.message && <span className="text-muted block mt-1">{item.message}</span>}</span>;
          } },
          { key: "version", label: "Version", render: (source) => <span>v{source.version}{source.status === "PUBLISHED" ? " · live" : ""}</span> },
          { key: "createdAt", label: "Uploaded", render: (source) => date(source.createdAt) },
        ]} actions={(source) => <div className="flex gap-1">
          <button className="icon-btn" aria-label={`View history for ${source.fileName}`} onClick={() => setDetails(source.id)}><FileClock size={17}/></button>
          {canManage && source.status !== "DELETED" && <>
            <button className="icon-btn" disabled={busy || isWorking(source)} aria-label={`Replace ${source.fileName}`} onClick={() => { setReplace(source); if (replacementInput.current) { replacementInput.current.value = ""; replacementInput.current.click(); } }}><Replace size={17}/></button>
            {source.status === "FAILED" && <button className="icon-btn" disabled={busy} aria-label={`Retry ${source.fileName}`} onClick={() => void action(source, "retry")}><RefreshCw size={17}/></button>}
            <button className="icon-btn" disabled={busy || isWorking(source)} aria-label={`Delete ${source.fileName}`} onClick={() => setRemove(source)}><Trash2 size={17}/></button>
          </>}
        </div>} /><Pagination data={query.data} page={page} setPage={setPage}/></Async>
      </section>
    </> : <LegacyFiles />}
    {remove && <Modal title="Delete knowledge source" onClose={() => !busy && setRemove(null)}><p className="text-muted mb-5">Delete {remove.fileName}? It is removed from search immediately, and the stored file is deleted.</p><div className="flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={() => setRemove(null)}>Cancel</button><button className="btn-primary" disabled={busy} onClick={() => void action(remove, "delete")}><Trash2 size={16}/> {busy ? "Queueing…" : "Delete source"}</button></div></Modal>}
    {details && <SourceHistory id={details} onClose={() => setDetails(null)}/>}
  </>;
}

function SourceHistory({ id, onClose }: { id: string; onClose: () => void }) {
  const { workspaceId } = useAuth();
  const path = `/knowledge/sources/${id}`;
  const query = useQuery<SourceDetails>({
    queryKey: [workspaceId, path], queryFn: () => api<SourceDetails>(path),
    refetchInterval: (result) => result.state.data && isWorking(result.state.data) ? 2000 : false,
  });
  const source = query.data;
  return <Modal title="Source processing & history" onClose={onClose}><Async query={query}>
    {source && <div className="space-y-5 min-w-0">
      <p className="break-all font-semibold">{source.fileName}</p>
      <p className="text-muted break-all">Source {id}</p>
      <div className="flex flex-wrap gap-3 items-center"><Badge value={source.status}/><span>{label(source.docType)}</span>
        <span>{source.pageCount} pages · {source.chunkCount} chunks</span>{source.costUsd > 0 && <span>${Number(source.costUsd).toFixed(4)}</span>}</div>
      {source.error && <p role="alert" className="break-words">{source.error}</p>}
      {(source.warnings || []).map((warning) => <p key={warning} className="info-strip break-words">{warning}</p>)}
      <section>
        <h3 className="font-semibold mb-2">Versions</h3>
        {(source.versions || []).map((v) => <div key={v.version} className="flex justify-between gap-3 py-1"><span>v{v.version} · {date(v.createdAt)}</span><Badge value={v.status}/></div>)}
      </section>
      <section>
        <h3 className="font-semibold mb-2">Pages</h3>
        {(source.pages || []).length ? <div className="flex flex-wrap gap-2">{(source.pages || []).map((pg) => <span key={pg.page} title={pg.provider}
          className={`badge ${pg.confidence < 0.6 ? "badge-amber" : "badge-neutral"}`}>p{pg.page} · {Math.round(pg.confidence * 100)}%</span>)}</div>
          : <p className="text-muted">Not parsed yet.</p>}
      </section>
    </div>}
  </Async></Modal>;
}

function LegacyFiles() {
  const list = useList("/files");
  const { canManage, workspaceId } = useAuth();
  const [remove, setRemove] = useState<Entity | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const toast = useToast();
  return <section className="panel min-w-0 max-w-full">
    <p className="p-5 text-muted">Files stored before knowledge ingestion remain available in this history. They have not been automatically ingested. Upload the original files to add them as knowledge sources.</p>
    {error !== null && <ErrorState error={error}/>}
    <Filters {...list} statuses={["UPLOADING", "STORED", "FAILED", "DELETED"]}/>
    <Async query={list.query}><DataTable dateFilter={false} data={list.query.data?.items || []} empty="No legacy files match the current filters." columns={[
      { key: "originalFileName", label: "File", render: (file) => <span className="whitespace-normal break-all">{file.originalFileName}</span> },
      { key: "fileExtension", label: "Type", render: (file) => String(file.fileExtension || "").toUpperCase() },
      { key: "fileSizeBytes", label: "Size", render: (file) => bytes(file.fileSizeBytes) },
      { key: "status", label: "Status", render: (file) => <Badge value={file.status}/> },
      { key: "createdAt", label: "Uploaded", render: (file) => date(file.createdAt) },
    ]} actions={canManage ? (file) => file.status === "STORED" ? <button className="icon-btn" aria-label={`Delete ${file.originalFileName}`} onClick={() => setRemove(file)}><Trash2 size={17}/></button> : null : undefined}/><Pagination data={list.query.data} page={list.page} setPage={list.setPage}/></Async>
    {remove && <Modal title="Delete stored file" onClose={() => !busy && setRemove(null)}><p className="text-muted mb-5">This removes the stored file but preserves its workspace history.</p><div className="flex justify-end gap-3"><button className="btn-secondary" disabled={busy} onClick={() => setRemove(null)}>Cancel</button><button className="btn-primary" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/files/${remove.id}`, { method: "DELETE" }); await queryClient.invalidateQueries({ queryKey: [workspaceId] }); toast("File deleted; history retained"); setRemove(null); } catch (nextError) { setError(nextError); setRemove(null); } finally { setBusy(false); } }}><Trash2 size={16}/> Delete file</button></div></Modal>}
  </section>;
}
