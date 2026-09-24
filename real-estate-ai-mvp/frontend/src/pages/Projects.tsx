import { useState } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import {
  Building2,
  FileText,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useApi } from "../hooks/useApi";
import { useList } from "../hooks/useList";
import { useAuth } from "../hooks/useAuth";
import {
  Async,
  Badge,
  DataTable,
  Details,
  Empty,
  ErrorState,
  Filters,
  Modal,
  PageHeader,
  Pagination,
  RecordForm,
  useToast,
} from "../components/ui";
import {
  projectFields,
  projectStatuses,
  unitFields,
  unitStatuses,
  documentFields,
} from "../features/fields";
import { api, write } from "../api/client";
import { queryClient } from "../services/query";
import { date, list, money, languages } from "../utils/format";
import type { Entity } from "../types";
export function ProjectTabs({ id }: { id: string }) {
  return (
    <div className="tabs">
      <NavLink end to={`/projects/${id}`}>
        Overview
      </NavLink>
      <NavLink to={`/projects/${id}/units`}>Unit inventory</NavLink>
      <NavLink to={`/projects/${id}/documents`}>Property knowledge</NavLink>
    </div>
  );
}
export function Projects() {
  const l = useList("/projects");
  const { canManage } = useAuth();
  const [create, setCreate] = useState(false);
  const toast = useToast();
  return (
    <>
      <PageHeader
        title="Projects & inventory"
        description="A clear view of the places your customers could call home."
        action={
          canManage && (
            <button className="btn-primary" onClick={() => setCreate(true)}>
              <Plus size={17} />
              New project
            </button>
          )
        }
      />
      <section className="panel">
        <Filters {...l} statuses={projectStatuses} />
        <Async query={l.query}>
          {list(l.query.data).length ? (
            <div className="project-grid">
              {list(l.query.data).map((p: Entity) => (
                <Link
                  key={p.id}
                  to={`/projects/${p.id}`}
                  className="project-card"
                >
                  <div className="project-art">
                    {p.mediaUrl && /^https?:\/\//.test(p.mediaUrl) ? (
                      <img
                        src={p.mediaUrl}
                        alt={p.name}
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <Building2 size={54} strokeWidth={1} />
                    )}
                    <Badge value={p.status} />
                  </div>
                  <div className="p-5">
                    <span className="eyebrow">
                      {p.developer || "RESIDENTIAL PROJECT"}
                    </span>
                    <h2 className="mt-2">{p.name}</h2>
                    <p className="flex items-center gap-1.5 mt-2 text-muted">
                      <MapPin size={14} />
                      {p.location}
                    </p>
                    <p className="text-muted text-sm mt-4 line-clamp-2">
                      {p.description ||
                        "Explore project details, current inventory and property knowledge."}
                    </p>
                    <div className="project-card-footer">
                      <span>Explore project</span>
                      <span>↗</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              title="No projects found"
              description="Create a project or adjust your filters."
            />
          )}
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
      {create && (
        <Modal title="Create project" onClose={() => setCreate(false)}>
          <RecordForm
            fields={projectFields}
            initial={{ status: "ACTIVE" }}
            submitLabel="Create project"
            onCancel={() => setCreate(false)}
            onSubmit={async (data) => {
              await write("/projects", data);
              await queryClient.invalidateQueries();
              setCreate(false);
              toast("Project created");
            }}
          />
        </Modal>
      )}
    </>
  );
}
export function ProjectDetail() {
  const { id = "" } = useParams();
  const q = useApi(`/projects/${id}`);
  const { canManage } = useAuth();
  const [edit, setEdit] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  return (
    <>
      <PageHeader
        title={q.data?.name || "Project overview"}
        back="/projects"
        description={q.data?.location}
        action={
          canManage && (
            <>
              <button className="btn-secondary" onClick={() => setEdit(true)}>
                <Pencil size={16} />
                Edit project
              </button>
              <button
                className="btn-secondary"
                onClick={() => setConfirm(true)}
              >
                {q.data?.status === "ACTIVE" ? "Deactivate" : "Activate"}
              </button>
            </>
          )
        }
      />
      <ProjectTabs id={id} />
      <Async query={q}>
        {q.data && (
          <div className="detail-columns">
            <section className="panel p-6">
              <div className="flex justify-between items-center mb-5">
                <h2>About this project</h2>
                <Badge value={q.data.status} />
              </div>
              <p className="readable mb-6">
                {q.data.description || "No description provided."}
              </p>
              <Details
                data={q.data}
                fields={[
                  "developer",
                  "location",
                  "possessionDate",
                  "amenities",
                  "mediaUrl",
                ]}
              />
            </section>
            <section className="panel p-6">
              <h2>Project workspace</h2>
              <p className="text-muted my-4">
                Keep availability and published property content current so
                every recommendation is grounded in the right information.
              </p>
              <Link className="shortcut" to={`/projects/${id}/units`}>
                <Building2 size={20} />
                <span>Explore inventory</span>→
              </Link>
              <Link className="shortcut" to={`/projects/${id}/documents`}>
                <FileText size={20} />
                <span>Manage property knowledge</span>→
              </Link>
            </section>
          </div>
        )}
      </Async>
      {edit && (
        <Modal title="Edit project" onClose={() => setEdit(false)}>
          <RecordForm
            fields={projectFields}
            initial={q.data}
            onCancel={() => setEdit(false)}
            onSubmit={async (data) => {
              await write(`/projects/${id}`, data, "PUT");
              await queryClient.invalidateQueries();
              setEdit(false);
              toast("Project updated");
            }}
          />
        </Modal>
      )}
      {confirm && (
        <Modal
          title={`${q.data?.status === "ACTIVE" ? "Deactivate" : "Activate"} this project?`}
          onClose={() => setConfirm(false)}
        >
          <p className="text-muted mb-5">
            This changes whether the project is active for your team. Existing
            records are preserved.
          </p>
          <RecordForm
            fields={[]}
            submitLabel="Confirm status change"
            onCancel={() => setConfirm(false)}
            onSubmit={async () => {
              await write(
                `/projects/${id}`,
                {
                  ...q.data,
                  status: q.data.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
                },
                "PUT",
              );
              await queryClient.invalidateQueries();
              setConfirm(false);
              toast("Project status updated");
            }}
          />
        </Modal>
      )}
    </>
  );
}
export function Units() {
  const { id = "" } = useParams();
  const p = useApi(`/projects/${id}`);
  const l = useList(`/projects/${id}/units`);
  const b = useApi(`/projects/${id}/buildings`);
  const floors = useApi(`/projects/${id}/floors`);
  const types = useApi(`/projects/${id}/unit-types`);
  const { canManage } = useAuth();
  const [edit, setEdit] = useState<Entity | null | undefined>();
  const [structure, setStructure] = useState("");
  const [history, setHistory] = useState("");
  const historyQuery = useApi(`/units/${history}/history`, !!history);
  const toast = useToast();
  return (
    <>
      <PageHeader
        title={p.data?.name || "Unit inventory"}
        back="/projects"
        description="Current availability, pricing, and the details that make a property fit."
        action={
          canManage && (
            <>
              <button
                className="btn-secondary"
                onClick={() => setStructure("buildings")}
              >
                Add building
              </button>
              <button className="btn-primary" onClick={() => setEdit(null)}>
                <Plus size={17} />
                New unit
              </button>
            </>
          )
        }
      />
      <ProjectTabs id={id} />
      <div className="summary-strip">
        <span>
          <strong>{list(b.data).length}</strong> buildings
        </span>
        <span>
          <strong>{list(floors.data).length}</strong> floors
        </span>
        <span>
          <strong>{list(types.data).length}</strong> unit types
        </span>
        <span>
          <strong>{l.query.data?.total || 0}</strong> matching units
        </span>
        {canManage && (
          <>
            <button
              className="text-link"
              onClick={() => setStructure("floors")}
            >
              Add floor
            </button>
            <button
              className="text-link"
              onClick={() => setStructure("unit-types")}
            >
              Add unit type
            </button>
          </>
        )}
      </div>
      <section className="panel">
        <Filters {...l} statuses={unitStatuses} />
        <Async query={l.query}>
          <DataTable
            data={list(l.query.data)}
            columns={[
              {
                key: "unitNumber",
                label: "Unit",
                render: (u) => <strong>{u.unitNumber}</strong>,
              },
              { key: "propertyType", label: "Type" },
              { key: "bhk", label: "BHK" },
              { key: "area", label: "Area", render: (u) => `${u.area} sq ft` },
              { key: "floor", label: "Floor" },
              { key: "price", label: "Price", render: (u) => money(u.price) },
              {
                key: "status",
                label: "Availability",
                render: (u) => <Badge value={u.status} />,
              },
            ]}
            actions={(u) => (
              <div className="flex gap-3">
                {canManage && (
                  <button className="text-link" onClick={() => setEdit(u)}>
                    Edit
                  </button>
                )}
                <button className="text-link" onClick={() => setHistory(u.id)}>
                  History
                </button>
              </div>
            )}
          />
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
      {edit !== undefined && (
        <Modal
          title={edit ? "Edit unit" : "Create unit"}
          onClose={() => setEdit(undefined)}
        >
          <RecordForm
            fields={unitFields(
              list(b.data),
              list(floors.data),
              list(types.data),
            )}
            initial={edit || { status: "AVAILABLE", propertyType: "APARTMENT" }}
            onCancel={() => setEdit(undefined)}
            onSubmit={async (data) => {
              await write(
                edit ? `/units/${edit.id}` : "/units",
                { ...data, projectId: id },
                edit ? "PUT" : "POST",
              );
              await queryClient.invalidateQueries();
              setEdit(undefined);
              toast("Inventory updated");
            }}
          />
        </Modal>
      )}
      {structure && (
        <Modal
          title={`Add ${structure === "unit-types" ? "unit type" : structure === "floors" ? "floor" : "building"}`}
          onClose={() => setStructure("")}
        >
          <RecordForm
            fields={
              structure === "floors"
                ? [
                    {
                      name: "buildingId",
                      label: "Building",
                      required: true,
                      options: list(b.data).map((v: Entity) => ({
                        value: v.id,
                        label: v.name,
                      })),
                    },
                    {
                      name: "number",
                      label: "Floor number",
                      type: "number",
                      required: true,
                      step: "1",
                    },
                  ]
                : [{ name: "name", label: "Name", required: true }]
            }
            onCancel={() => setStructure("")}
            onSubmit={async (data) => {
              await write(`/projects/${id}/${structure}`, data);
              await queryClient.invalidateQueries();
              setStructure("");
              toast("Project structure updated");
            }}
          />
        </Modal>
      )}
      {history && (
        <Modal title="Unit status history" onClose={() => setHistory("")}>
          <Async query={historyQuery}>
            <DataTable
              data={list(historyQuery.data)}
              columns={[
                {
                  key: "status",
                  label: "Status",
                  render: (h) => <Badge value={h.status || h.newStatus} />,
                },
                {
                  key: "createdAt",
                  label: "Changed",
                  render: (h) => date(h.createdAt),
                },
                { key: "notes", label: "Notes" },
              ]}
            />
          </Async>
        </Modal>
      )}
    </>
  );
}
export function Documents() {
  const { id = "" } = useParams();
  const p = useApi(`/projects/${id}`);
  const documentList = useList(`/projects/${id}/documents`);
  const q = documentList.query;
  const { canManage } = useAuth();
  const [selected, setSelected] = useState<Entity | null>(null);
  const [create, setCreate] = useState(false);
  const [mode, setMode] = useState("view");
  const [action, setAction] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [processingError, setProcessingError] = useState<unknown>(null);
  const [processingResult, setProcessingResult] = useState<any>(null);
  const detail = useApi(`/documents/${selected?.id}`, !!selected);
  const versions = useApi(
    `/documents/${selected?.id}/versions`,
    !!selected && mode === "versions",
  );
  const toast = useToast();
  const doc = detail.data || selected;
  return (
    <>
      <PageHeader
        title={p.data?.name || "Property knowledge"}
        back="/projects"
        description="One source of truth. Original PDFs, editable content, and published knowledge."
        action={
          canManage && (
            <button className="btn-primary" onClick={() => setCreate(true)}>
              <Plus size={17} />
              Register PDF
            </button>
          )
        }
      />
      <ProjectTabs id={id} />
      <div className="info-strip">
        <FileText size={18} />
        <span>
          Register a PDF from your storage service. Only published content is
          available to the knowledge integration.
        </span>
      </div>
      <section className="panel">
        <Filters {...documentList} statuses={["DRAFT", "PUBLISHED"]} />
        <Async query={q}>
          <DataTable
            data={list(q.data)}
            columns={[
              {
                key: "title",
                label: "Document",
                render: (d) => (
                  <button
                    className="text-link font-semibold"
                    onClick={() => {
                      setSelected(d);
                      setMode("view");
                      setProcessingError(null);
                      setProcessingResult(null);
                    }}
                  >
                    {d.title}
                  </button>
                ),
              },
              {
                key: "language",
                label: "Language",
                render: (d) =>
                  languages.find((l) => l.value === d.language)?.label ||
                  d.language,
              },
              {
                key: "status",
                label: "Content",
                render: (d) => <Badge value={d.status} />,
              },
              {
                key: "processingStatus",
                label: "Processing",
                render: (d) => <Badge value={d.processingStatus} />,
              },
              {
                key: "updatedAt",
                label: "Last updated",
                render: (d) => date(d.updatedAt),
              },
            ]}
          />
          <Pagination
            data={q.data}
            page={documentList.page}
            setPage={documentList.setPage}
          />
        </Async>
      </section>
      {create && (
        <Modal title="Register property PDF" onClose={() => setCreate(false)}>
          <RecordForm
            fields={documentFields}
            initial={{ language: "en" }}
            onCancel={() => setCreate(false)}
            submitLabel="Register document"
            onSubmit={async (data) => {
              await write("/documents", { ...data, projectId: id });
              await queryClient.invalidateQueries();
              setCreate(false);
              toast("Document registered as a draft");
            }}
          />
        </Modal>
      )}
      {selected && (
        <Modal
          title={doc?.title || "Property document"}
          onClose={() => setSelected(null)}
        >
          <div className="flex gap-3 flex-wrap mb-5">
            <button
              className={mode === "view" ? "btn-primary" : "btn-secondary"}
              onClick={() => setMode("view")}
            >
              Read content
            </button>
            {canManage && (
              <button
                className={mode === "edit" ? "btn-primary" : "btn-secondary"}
                onClick={() => setMode("edit")}
              >
                Edit content
              </button>
            )}
            <button
              className={mode === "versions" ? "btn-primary" : "btn-secondary"}
              onClick={() => setMode("versions")}
            >
              Version history
            </button>
          </div>
          <Async query={detail}>
            {mode === "view" && (
              <>
                {processingError != null && (
                  <ErrorState error={processingError} />
                )}
                <div className="flex gap-3 items-center flex-wrap mb-5">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={refreshing}
                    onClick={async () => {
                      setRefreshing(true);
                      setProcessingError(null);
                      try {
                        const result = await api(
                          `/documents/${selected.id}/processing-status`,
                        );
                        setProcessingResult(result);
                        await queryClient.invalidateQueries();
                        toast(
                          result.mock
                            ? "Processing status refreshed using the demo adapter"
                            : "Latest processing status retrieved",
                        );
                      } catch (error) {
                        setProcessingError(error);
                      } finally {
                        setRefreshing(false);
                      }
                    }}
                  >
                    <RefreshCw
                      size={16}
                      className={refreshing ? "animate-spin" : ""}
                    />
                    {refreshing
                      ? "Checking provider…"
                      : "Refresh processing status"}
                  </button>
                  {processingResult?.mock && <Badge value="SIMULATED" />}
                  {processingResult?.status && (
                    <Badge value={processingResult.status} />
                  )}
                </div>
                <Details
                  data={doc || {}}
                  fields={[
                    "fileName",
                    "storageReference",
                    "language",
                    "pageReference",
                    "status",
                    "processingStatus",
                    "processingError",
                  ]}
                />
                <div className="content-reader mt-5">
                  {typeof doc?.content === "string"
                    ? doc.content
                    : "No readable content provided."}
                </div>
                {canManage && (
                  <div className="flex gap-2 mt-5">
                    <button
                      className="btn-primary"
                      onClick={() =>
                        setAction(
                          doc?.status === "PUBLISHED" ? "unpublish" : "publish",
                        )
                      }
                    >
                      {doc?.status === "PUBLISHED"
                        ? "Unpublish"
                        : "Publish content"}
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => setAction("reindex")}
                      disabled={doc?.status !== "PUBLISHED"}
                    >
                      Re-index published content
                    </button>
                  </div>
                )}
              </>
            )}
            {mode === "edit" && (
              <RecordForm
                fields={documentFields.filter((f) =>
                  ["content", "language", "pageReference"].includes(f.name),
                )}
                initial={doc || {}}
                submitLabel="Save content draft"
                onSubmit={async (data) => {
                  await write(`/documents/${selected.id}/content`, data, "PUT");
                  await queryClient.invalidateQueries();
                  setMode("view");
                  toast("New content version saved");
                }}
              />
            )}
            {mode === "versions" && (
              <Async query={versions}>
                {list(versions.data).map((v: Entity, i: number) => (
                  <article key={v.id || i} className="version-card">
                    <strong>
                      Version {v.version || v.versionNumber || i + 1}
                    </strong>
                    <small>{date(v.createdAt)}</small>
                    <div className="content-reader">
                      {v.content || v.title || v.status}
                    </div>
                  </article>
                ))}
                {!list(versions.data).length && (
                  <Empty
                    title="No earlier versions"
                    description="Content changes are versioned automatically."
                  />
                )}
              </Async>
            )}
          </Async>
        </Modal>
      )}
      {action && selected && (
        <Modal
          title={`${action === "reindex" ? "Re-index" : action === "publish" ? "Publish" : "Unpublish"} document`}
          onClose={() => setAction("")}
        >
          <p className="text-muted mb-5">
            {action === "unpublish"
              ? "Remove this content from production knowledge retrieval?"
              : "Send this published content to the configured knowledge service? Mock mode is clearly identified in service results."}
          </p>
          <RecordForm
            fields={[]}
            submitLabel="Confirm"
            onCancel={() => setAction("")}
            onSubmit={async () => {
              const r = await write(`/documents/${selected.id}/${action}`, {});
              await queryClient.invalidateQueries();
              setAction("");
              toast(
                r?.mock
                  ? "Completed using the simulated knowledge adapter"
                  : "Document request completed",
              );
            }}
          />
        </Modal>
      )}
    </>
  );
}
