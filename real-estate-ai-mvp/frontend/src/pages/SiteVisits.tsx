import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { CalendarDays, Plus } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useList } from "../hooks/useList";
import {
  Async,
  Badge,
  DataTable,
  Details,
  Filters,
  Modal,
  PageHeader,
  Pagination,
  RecordForm,
  useToast,
} from "../components/ui";
import {
  visitFields,
  visitStatuses,
  leadOptions,
  projectOptions,
  availableUnitOptions,
} from "../features/fields";
import { EntityName } from "../components/AsyncSelect";
import { write } from "../api/client";
import { queryClient } from "../services/query";
import { date, list } from "../utils/format";
import type { Entity } from "../types";

function visitStatusPayload(visit: Record<string, any>, status: string) {
  return {
    leadId: visit.leadId,
    projectId: visit.projectId,
    unitId: visit.unitId ?? null,
    agentId: visit.agentId,
    scheduledAt: visit.scheduledAt,
    durationMinutes: visit.durationMinutes,
    notes: visit.notes ?? null,
    ...(visit.confirmationStatus
      ? { confirmationStatus: visit.confirmationStatus }
      : {}),
    status,
  };
}

export function useVisitOptions() {
  const members = useApi("/members");
  return {
    members: list(members.data),
  };
}
export function VisitForm({
  initial = {},
  onSave,
  onCancel,
}: {
  initial?: Record<string, any>;
  onSave: (d: Record<string, any>) => Promise<void>;
  onCancel: () => void;
}) {
  const o = useVisitOptions();
  return (
    <RecordForm
      fields={visitFields([], [], o.members, []).map((field) => ({
        ...field,
        remote:
          field.name === "leadId"
            ? leadOptions
            : field.name === "projectId"
              ? projectOptions
              : field.name === "unitId"
                ? availableUnitOptions
                : undefined,
      }))}
      initial={{
        durationMinutes: 60,
        status: "CONFIRMED",
        confirmationStatus: "PENDING",
        ...initial,
      }}
      submitLabel={initial.id ? "Save visit" : "Confirm booking"}
      onCancel={onCancel}
      onSubmit={async (d) => {
        if (!initial.id && new Date(d.scheduledAt).getTime() <= Date.now())
          throw new Error("Choose a date and time in the future.");
        await onSave(d);
      }}
    />
  );
}
export function SiteVisits() {
  const l = useList("/site-visits", "scheduledAt,asc");
  const [params] = useSearchParams();
  const [create, setCreate] = useState(params.get("create") === "true");
  const [view, setView] = useState("schedule");
  const o = useVisitOptions();
  const navigate = useNavigate();
  const toast = useToast();
  const name = (items: Entity[], id: string) =>
    items.find((x) => x.id === id)?.name || "Not assigned";
  return (
    <>
      <PageHeader
        title="Site visits"
        description="Make the first visit feel like the start of something good."
        action={
          <button className="btn-primary" onClick={() => setCreate(true)}>
            <Plus size={17} />
            Book a visit
          </button>
        }
      />
      <section className="panel">
        <div className="flex items-center justify-between flex-wrap">
          <Filters
            {...l}
            statuses={visitStatuses}
            sortOptions={[
              { value: "scheduledAt,asc", label: "Visit date: earliest first" },
              { value: "scheduledAt,desc", label: "Visit date: latest first" },
            ]}
          />
          <div className="segmented m-5">
            <button
              className={view === "schedule" ? "selected" : ""}
              onClick={() => setView("schedule")}
            >
              Schedule
            </button>
            <button
              className={view === "table" ? "selected" : ""}
              onClick={() => setView("table")}
            >
              Table
            </button>
          </div>
        </div>
        <Async query={l.query}>
          {view === "schedule" && list(l.query.data).length ? (
            <div className="visit-schedule">
              {list(l.query.data).map((v: Entity) => (
                <Link
                  key={v.id}
                  to={`/site-visits/${v.id}`}
                  className="visit-slot"
                >
                  <div className="visit-date">
                    <span>
                      {new Date(v.scheduledAt).toLocaleDateString("en-IN", {
                        month: "short",
                      })}
                    </span>
                    <strong>{new Date(v.scheduledAt).getDate()}</strong>
                  </div>
                  <div className="flex-1">
                    <h3>
                      <EntityName
                        path="/leads"
                        id={v.leadId}
                        fallback={v.leadName}
                      />
                    </h3>
                    <p>
                      <EntityName
                        path="/projects"
                        id={v.projectId}
                        fallback={v.projectName}
                      />
                    </p>
                    <small>
                      {date(v.scheduledAt)} · {v.durationMinutes} minutes ·{" "}
                      {v.agentName || name(o.members, v.agentId)}
                    </small>
                  </div>
                  <Badge value={v.status} />
                  <CalendarDays size={19} className="text-muted" />
                </Link>
              ))}
            </div>
          ) : (
            <DataTable
              data={list(l.query.data)}
              columns={[
                {
                  key: "scheduledAt",
                  label: "Date & time",
                  render: (v) => (
                    <Link className="text-link" to={`/site-visits/${v.id}`}>
                      {date(v.scheduledAt)}
                    </Link>
                  ),
                },
                {
                  key: "leadId",
                  label: "Customer",
                  render: (v) => (
                    <EntityName
                      path="/leads"
                      id={v.leadId}
                      fallback={v.leadName}
                    />
                  ),
                },
                {
                  key: "projectId",
                  label: "Project",
                  render: (v) => (
                    <EntityName
                      path="/projects"
                      id={v.projectId}
                      fallback={v.projectName}
                    />
                  ),
                },
                {
                  key: "agentId",
                  label: "Agent",
                  render: (v) => v.agentName || name(o.members, v.agentId),
                },
                {
                  key: "status",
                  label: "Status",
                  render: (v) => <Badge value={v.status} />,
                },
              ]}
            />
          )}
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
      {create && (
        <Modal title="Book a site visit" onClose={() => setCreate(false)}>
          <VisitForm
            initial={{ leadId: params.get("leadId") || "" }}
            onCancel={() => setCreate(false)}
            onSave={async (d) => {
              const v = await write("/site-visits", d);
              await queryClient.invalidateQueries();
              setCreate(false);
              toast("Site visit booked");
              navigate(`/site-visits/${v.id}`);
            }}
          />
        </Modal>
      )}
    </>
  );
}
export function SiteVisitDetail() {
  const { id } = useParams();
  const q = useApi(`/site-visits/${id}`);
  const o = useVisitOptions();
  const [edit, setEdit] = useState(false);
  const [action, setAction] = useState("");
  const toast = useToast();
  const d = q.data || {};
  const customer = useApi(`/leads/${d.leadId}`, !!d.leadId);
  const project = useApi(`/projects/${d.projectId}`, !!d.projectId);
  const name = (items: Entity[], value: string) =>
    items.find((x) => x.id === value)?.name || "Not assigned";
  return (
    <>
      <PageHeader
        title="Site visit details"
        back="/site-visits"
        description={date(d.scheduledAt)}
        action={
          <button className="btn-primary" onClick={() => setEdit(true)}>
            Edit / reschedule
          </button>
        }
      />
      <Async query={q}>
        <div className="summary-strip">
          <Badge value={d.status} />
          <span>{d.durationMinutes} minutes</span>
          <span>
            Customer confirmation: <Badge value={d.confirmationStatus} />
          </span>
          <span>
            Agent notification: <Badge value={d.notificationStatus} />
          </span>
          <span>
            Customer notification:{" "}
            <Badge value={d.customerNotificationStatus || "NOT_RECORDED"} />
          </span>
        </div>
        <div className="detail-columns">
          <section className="panel p-6">
            <h2 className="mb-5">The visit plan</h2>
            <Details
              data={{
                customer: d.leadName || customer.data?.name || d.leadId,
                project: d.projectName || project.data?.name || d.projectId,
                agent: d.agentName || name(o.members, d.agentId),
                scheduled: date(d.scheduledAt),
                duration: `${d.durationMinutes} minutes`,
                notes: d.notes,
              }}
              fields={[
                "customer",
                "project",
                "agent",
                "scheduled",
                "duration",
                "notes",
              ]}
            />
            <div className="flex flex-wrap gap-3 mt-6">
              <Link className="btn-secondary" to={`/leads/${d.leadId}`}>
                View lead
              </Link>
              <Link className="btn-secondary" to={`/projects/${d.projectId}`}>
                View project
              </Link>
              <Link
                className="btn-primary"
                to={`/handovers?create=true&leadId=${d.leadId}&appointmentId=${id}&projectId=${d.projectId}&agentId=${d.agentId}`}
              >
                Prepare handover →
              </Link>
            </div>
          </section>
          <section className="panel p-6 h-fit">
            <h2>After the visit</h2>
            <p className="text-muted mt-3 mb-5">
              Keep the team informed and the next step clear.
            </p>
            <div className="flex flex-col gap-3">
              {[
                ["COMPLETED", "Mark completed"],
                ["NO_SHOW", "Mark no-show"],
                ["CANCELLED", "Cancel visit"],
              ].map(([status, text]) => (
                <button
                  key={status}
                  className={
                    status === "CANCELLED" ? "btn-danger" : "btn-secondary"
                  }
                  onClick={() => setAction(status)}
                  disabled={d.status === status}
                >
                  {text}
                </button>
              ))}
            </div>
          </section>
        </div>
      </Async>
      {edit && (
        <Modal title="Edit / reschedule visit" onClose={() => setEdit(false)}>
          <VisitForm
            initial={d}
            onCancel={() => setEdit(false)}
            onSave={async (data) => {
              const timeChanged =
                new Date(data.scheduledAt).getTime() !==
                new Date(d.scheduledAt).getTime();
              if (
                timeChanged &&
                new Date(data.scheduledAt).getTime() <= Date.now()
              )
                throw new Error("Rescheduled visits must be in the future.");
              await write(
                `/site-visits/${id}`,
                {
                  ...data,
                  status: timeChanged ? "RESCHEDULED" : data.status,
                },
                "PUT",
              );
              await queryClient.invalidateQueries();
              setEdit(false);
              toast("Site visit updated");
            }}
          />
        </Modal>
      )}
      {action && (
        <Modal title="Update visit status?" onClose={() => setAction("")}>
          <p className="text-muted mb-5">
            The visit status will change to{" "}
            {action.toLowerCase().replaceAll("_", " ")}. Your team’s schedule
            and notification history will be updated.
          </p>
          <RecordForm
            fields={[]}
            submitLabel="Confirm status change"
            onCancel={() => setAction("")}
            onSubmit={async () => {
              await write(
                `/site-visits/${id}`,
                visitStatusPayload(d, action),
                "PUT",
              );
              await queryClient.invalidateQueries();
              setAction("");
              toast("Visit status updated");
            }}
          />
        </Modal>
      )}
    </>
  );
}
