import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { CalendarDays, Handshake, Phone, Plus, Sparkles } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useList } from "../hooks/useList";
import {
  Async,
  Badge,
  DataTable,
  Details,
  Empty,
  Filters,
  Modal,
  PageHeader,
  Pagination,
  RecordForm,
  useToast,
} from "../components/ui";
import { leadFields, leadStatuses } from "../features/fields";
import { write } from "../api/client";
import { queryClient } from "../services/query";
import { date, label, languages, list, money } from "../utils/format";
import type { Entity } from "../types";
import { ContactLink } from "../components/ContactLink";
export function Leads() {
  const l = useList("/leads");
  const members = useApi("/members");
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(params.get("create") === "true");
  const navigate = useNavigate();
  const toast = useToast();
  return (
    <>
      <PageHeader
        title="Your leads"
        description="The people behind your pipeline. Give every conversation a meaningful next step."
        action={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus size={17} />
            Add lead
          </button>
        }
      />
      <section className="panel">
        <Filters {...l} statuses={leadStatuses} />
        <Async query={l.query}>
          <DataTable
            data={list(l.query.data)}
            columns={[
              {
                key: "name",
                label: "Customer",
                render: (r) => (
                  <div className="person-cell">
                    <Link className="avatar" to={`/leads/${r.id}`} aria-label={`View ${r.name}`}>
                      {r.name?.slice(0, 2).toUpperCase()}
                    </Link>
                    <span>
                      <Link to={`/leads/${r.id}`}><strong>{r.name}</strong></Link>
                      <small>{r.phone ? <ContactLink kind="phone" value={String(r.phone)} /> : "Not provided"}</small>
                    </span>
                  </div>
                ),
              },
              {
                key: "status",
                label: "Stage",
                render: (r) => <Badge value={r.status} />,
              },
              { key: "location", label: "Preferred location" },
              {
                key: "budgetMax",
                label: "Budget",
                render: (r) =>
                  r.budgetMax ? money(r.budgetMax) : "Not specified",
              },
              {
                key: "language",
                label: "Language",
                render: (r) =>
                  languages.find((l) => l.value === r.language)?.label ||
                  r.language,
              },
              {
                key: "source",
                label: "Source",
                render: (r) => label(r.source),
              },
              {
                key: "followUpAt",
                label: "Follow-up",
                render: (r) => date(r.followUpAt),
              },
            ]}
          />
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
      {open && (
        <Modal
          title="Create lead"
          onClose={() => {
            setOpen(false);
            setParams({});
          }}
        >
          <RecordForm
            fields={leadFields(list(members.data))}
            initial={{
              language: "en",
              status: "NEW",
              source: "WEBSITE",
              intent: "BUY",
            }}
            submitLabel="Create lead"
            onCancel={() => setOpen(false)}
            onSubmit={async (data) => {
              const created = await write("/leads", data);
              await queryClient.invalidateQueries();
              setOpen(false);
              toast("Lead created");
              navigate(`/leads/${created.id}`);
            }}
          />
        </Modal>
      )}
    </>
  );
}
export function LeadDetail() {
  const { id = "" } = useParams();
  const q = useApi(`/leads/${id}`);
  const members = useApi("/members");
  const [edit, setEdit] = useState(false);
  const [call, setCall] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();
  const d = q.data || {};
  return (
    <>
      <PageHeader
        title={d.name || "Lead details"}
        back="/leads"
        description={d.phone || d.email ? <span className="contact-line">
          {d.phone && <ContactLink kind="phone" value={String(d.phone)} />}
          {d.phone && d.email && " · "}
          {d.email && <ContactLink kind="email" value={String(d.email)} />}
        </span> : undefined}
        action={
          <>
            <button className="btn-secondary" onClick={() => setEdit(true)}>
              Edit lead
            </button>
            <button className="btn-primary" onClick={() => setCall(true)}>
              <Phone size={16} />
              Start call
            </button>
          </>
        }
      />
      <Async query={q}>
        <div className="summary-strip">
          <Badge value={d.status} />
          <span>
            {languages.find((l) => l.value === d.language)?.label || d.language}
          </span>
          <span>{label(d.source)}</span>
          <span>
            Assigned to{" "}
            <strong>
              {list(members.data).find(
                (m: Entity) => m.id === d.assignedAgentId,
              )?.name || "Unassigned"}
            </strong>
          </span>
        </div>
        <div className="workflow-actions">
          <Link to={`/recommendations?leadId=${id}`}>
            <Sparkles size={18} />
            Find matching properties →
          </Link>
          <Link to={`/site-visits?create=true&leadId=${id}`}>
            <CalendarDays size={18} />
            Book a site visit →
          </Link>
          <Link to={`/handovers?create=true&leadId=${id}`}>
            <Handshake size={18} />
            Prepare handover →
          </Link>
        </div>
        <div className="detail-columns">
          <div className="space-y-6">
            <section className="panel p-6">
              <h2 className="mb-5">Customer requirements</h2>
              <Details
                data={d}
                fields={[
                  "intent",
                  "budgetMin",
                  "budgetMax",
                  "location",
                  "propertyType",
                  "bhk",
                  "areaMin",
                  "areaMax",
                  "possessionTimeline",
                  "purpose",
                  "urgency",
                  "tags",
                ]}
              />
              <div className="content-reader mt-5">
                {d.notes || "No initial notes recorded."}
              </div>
            </section>
            <section className="panel p-6">
              <h2 className="mb-5">Conversation notes</h2>
              <RecordForm
                fields={[
                  {
                    name: "text",
                    label: "Add a note",
                    type: "textarea",
                    required: true,
                    wide: true,
                  },
                ]}
                submitLabel="Add note"
                key={list(d.notesHistory).length}
                onSubmit={async (data) => {
                  await write(`/leads/${id}/notes`, data);
                  await queryClient.invalidateQueries();
                  toast("Note added");
                }}
              />
              {list(d.notesHistory).map((n: Entity) => (
                <article className="note-card" key={n.id}>
                  <p>{n.text || n.content}</p>
                  <small>{date(n.createdAt)}</small>
                </article>
              ))}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>Suggested properties</h2>
              </div>
              <DataTable
                data={list(d.recommendations).map((r: any, i: number) => ({
                  ...r,
                  id: r.id || r.unit?.id || String(i),
                }))}
                columns={[
                  {
                    key: "project",
                    label: "Project",
                    render: (r) => r.project?.name || r.projectName,
                  },
                  {
                    key: "unit",
                    label: "Unit",
                    render: (r) => r.unit?.unitNumber || r.unitNumber,
                  },
                  { key: "reason", label: "Match context" },
                ]}
              />
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>Call history</h2>
              </div>
              <DataTable
                data={list(d.calls)}
                columns={[
                  {
                    key: "createdAt",
                    label: "Conversation",
                    render: (c) => (
                      <Link className="text-link" to={`/calls/${c.id}`}>
                        {date(c.createdAt)}
                      </Link>
                    ),
                  },
                  {
                    key: "status",
                    label: "Status",
                    render: (c) => <Badge value={c.status} />,
                  },
                  { key: "outcome", label: "Outcome" },
                ]}
              />
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>Site visits & handovers</h2>
              </div>
              <DataTable
                data={list(d.siteVisits)}
                columns={[
                  {
                    key: "scheduledAt",
                    label: "Visit",
                    render: (v) => (
                      <Link className="text-link" to={`/site-visits/${v.id}`}>
                        {date(v.scheduledAt)}
                      </Link>
                    ),
                  },
                  {
                    key: "status",
                    label: "Status",
                    render: (v) => <Badge value={v.status} />,
                  },
                ]}
              />
              <div className="p-5 border-t">
                {list(d.handovers).length ? (
                  list(d.handovers).map((h: Entity) => (
                    <div key={h.id} className="flex justify-between gap-4 py-2">
                      <span>Handover · {date(h.createdAt)}</span>
                      <Badge value={h.status} />
                    </div>
                  ))
                ) : (
                  <p className="text-muted">No handover yet.</p>
                )}
              </div>
            </section>
          </div>
          <section className="panel h-fit">
            <div className="panel-heading">
              <h2>Activity timeline</h2>
            </div>
            {list(d.activities).length ? (
              <div className="activity-list">
                {list(d.activities).map((a: Entity) => (
                  <div className="activity-row" key={a.id}>
                    <span className="activity-dot" />
                    <div>
                      <strong>
                        {a.description || label(a.action || a.type)}
                      </strong>
                      <small>{date(a.createdAt)}</small>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="A fresh start"
                description="Updates to this lead will appear here."
              />
            )}
          </section>
        </div>
      </Async>
      {edit && (
        <Modal title="Edit lead" onClose={() => setEdit(false)}>
          <RecordForm
            fields={leadFields(list(members.data))}
            initial={d}
            onCancel={() => setEdit(false)}
            onSubmit={async (data) => {
              await write(`/leads/${id}`, data, "PUT");
              await queryClient.invalidateQueries();
              setEdit(false);
              toast("Lead updated");
            }}
          />
        </Modal>
      )}
      {call && (
        <Modal title="Start an outbound call?" onClose={() => setCall(false)}>
          <p className="text-muted mb-5">
            The configured voice service will contact {d.name} at {d.phone ? <ContactLink kind="phone" value={String(d.phone)} /> : "the saved number"}. In
            demo mode this produces a simulated conversation.
          </p>
          <RecordForm
            fields={[]}
            submitLabel="Start outbound call"
            onCancel={() => setCall(false)}
            onSubmit={async () => {
              const result = await write("/calls", { leadId: id });
              await queryClient.invalidateQueries();
              setCall(false);
              toast(result.mock ? "Simulated call created" : "Call requested");
              navigate(`/calls/${result.id}`);
            }}
          />
        </Modal>
      )}
    </>
  );
}
