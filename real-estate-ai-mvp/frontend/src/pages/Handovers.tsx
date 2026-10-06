import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Handshake, Plus } from "../components/icons";
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
  entityOptions,
  leadOptions,
  projectOptions,
  availableUnitOptions,
  appointmentOptions,
} from "../features/fields";
import { EntityName } from "../components/AsyncSelect";
import { write } from "../api/client";
import { queryClient } from "../services/query";
import { date, list, options } from "../utils/format";
import { useVisitOptions } from "./SiteVisits";
import { RichContent } from "./Calls";
import type { Entity, Field } from "../types";
export function Handovers() {
  const l = useList("/handovers");
  const [params] = useSearchParams();
  const [edit, setEdit] = useState<Entity | null | undefined>(
    params.get("create") === "true" ? null : undefined,
  );
  const [selected, setSelected] = useState<Entity | null>(null);
  const detail = useApi(`/handovers/${selected?.id}`, !!selected);
  const o = useVisitOptions();
  const toast = useToast();
  const fields: Field[] = [
    {
      name: "leadId",
      label: "Lead",
      required: true,
      remote: leadOptions,
    },
    {
      name: "agentId",
      label: "Assigned human agent",
      required: true,
      options: entityOptions(
        o.members.filter((m: Entity) => m.role === "REAL_ESTATE_AGENT"),
      ),
    },
    {
      name: "projectId",
      label: "Selected project",
      remote: projectOptions,
    },
    {
      name: "unitId",
      label: "Selected unit",
      dependsOn: "projectId",
      remote: availableUnitOptions,
      hint: "Select a project to see its available units.",
    },
    {
      name: "appointmentId",
      label: "Site visit",
      dependsOn: "leadId",
      remote: appointmentOptions,
    },
    {
      name: "status",
      label: "Handover status",
      required: true,
      options: options(["PENDING", "ASSIGNED", "ACCEPTED", "COMPLETED"]),
    },
    {
      name: "questions",
      label: "Customer questions",
      type: "textarea",
      wide: true,
    },
    {
      name: "notes",
      label: "Handover notes",
      type: "textarea",
      wide: true,
      required: true,
    },
  ];
  const d = detail.data || selected;
  const chosenProject = useApi(`/projects/${d?.projectId}`, !!d?.projectId);
  const chosenUnit = useApi(`/units/${d?.unitId}`, !!d?.unitId);
  const chosenVisit = useApi(
    `/site-visits/${d?.appointmentId}`,
    !!d?.appointmentId,
  );
  return (
    <>
      <PageHeader
        title="Human handovers"
        description="Pass the whole story, so the next conversation starts in the right place."
        action={
          <button className="btn-primary" onClick={() => setEdit(null)}>
            <Plus size={17} />
            Create handover
          </button>
        }
      />
      <div className="info-strip">
        <Handshake size={19} />
        <span>
          EstraOS supports the journey through qualification and site visits.
          Your human real-estate agent handles later buying, financial, and
          legal activities.
        </span>
      </div>
      <section className="panel">
        <Filters
          {...l}
          statuses={["PENDING", "ASSIGNED", "ACCEPTED", "COMPLETED"]}
        />
        <Async query={l.query}>
          <DataTable
            dateFilter={false}
            data={list(l.query.data)}
            columns={[
              {
                key: "leadId",
                label: "Customer",
                render: (h) => (
                  <button
                    className="text-link font-semibold"
                    onClick={() => setSelected(h)}
                  >
                    <EntityName
                      path="/leads"
                      id={h.leadId}
                      fallback={h.leadName}
                    />
                  </button>
                ),
              },
              {
                key: "agentId",
                label: "Assigned agent",
                render: (h) =>
                  h.agentName ||
                  o.members.find((x: Entity) => x.id === h.agentId)?.name ||
                  "Unassigned",
              },
              {
                key: "status",
                label: "Status",
                render: (h) => <Badge value={h.status} />,
              },
              {
                key: "createdAt",
                label: "Handed over",
                render: (h) => date(h.handoverAt || h.createdAt),
              },
              { key: "notes", label: "Notes" },
            ]}
            actions={(h) => (
              <button className="text-link" onClick={() => setEdit(h)}>
                Edit
              </button>
            )}
          />
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
      {edit !== undefined && (
        <Modal
          title={edit ? "Update handover" : "Prepare human handover"}
          onClose={() => setEdit(undefined)}
        >
          <RecordForm
            fields={fields}
            initial={
              edit || {
                status: "ASSIGNED",
                leadId: params.get("leadId") || "",
                appointmentId: params.get("appointmentId") || "",
                projectId: params.get("projectId") || "",
                agentId: params.get("agentId") || "",
              }
            }
            submitLabel={edit ? "Save handover" : "Create handover"}
            onCancel={() => setEdit(undefined)}
            onSubmit={async (data) => {
              await write(
                edit ? `/handovers/${edit.id}` : "/handovers",
                data,
                edit ? "PUT" : "POST",
              );
              await queryClient.invalidateQueries();
              setEdit(undefined);
              toast("Handover saved and assignment notification recorded");
            }}
          />
        </Modal>
      )}
      {selected && (
        <Modal title="The complete handover" onClose={() => setSelected(null)}>
          <Async query={detail}>
            <div className="summary-strip">
              <Badge value={d?.status} />
              <Link className="text-link" to={`/leads/${d?.leadId}`}>
                Open lead →
              </Link>
            </div>
            <h3 className="mb-3">Customer requirements</h3>
            <Details
              data={d?.lead || {}}
              fields={[
                "name",
                "phone",
                "email",
                "language",
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
                "notes",
              ]}
            />
            <h3 className="mt-6 mb-3">Assigned agent & selected property</h3>
            <Details
              data={{
                assignedAgent:
                  d?.agentName ||
                  d?.agent?.name ||
                  o.members.find((member: Entity) => member.id === d?.agentId)
                    ?.name ||
                  d?.agentId,
                project:
                  d?.project?.name || chosenProject.data?.name || d?.projectId,
                unit:
                  d?.unit?.unitNumber ||
                  chosenUnit.data?.unitNumber ||
                  d?.unitId,
                unitArea:
                  (d?.unit?.area ?? chosenUnit.data?.area)
                    ? `${d?.unit?.area ?? chosenUnit.data?.area} sq ft`
                    : undefined,
                visit: d?.appointmentId
                  ? date(
                      chosenVisit.data?.scheduledAt ||
                        d?.appointment?.scheduledAt,
                    )
                  : "No selected visit",
                handoverAt: d?.handoverAt ? date(d.handoverAt) : "Not recorded",
                lastUpdated: date(d?.updatedAt),
              }}
              fields={[
                "assignedAgent",
                "project",
                "unit",
                "unitArea",
                "visit",
                "handoverAt",
                "lastUpdated",
              ]}
            />
            <h3 className="mt-6 mb-3">Customer questions & handover notes</h3>
            <RichContent value={d?.questions} />
            <div className="mt-3">
              <RichContent value={d?.notes} />
            </div>
            <h3 className="mt-6 mb-3">Conversation context</h3>
            {list(d?.calls).map((c: Entity) => (
              <div key={c.id} className="note-card">
                <Link className="text-link mb-3" to={`/calls/${c.id}`}>
                  Transcript · {date(c.createdAt)} →
                </Link>
                <RichContent value={c.summary} />
              </div>
            ))}
            <h3 className="mt-6 mb-3">Recommended properties</h3>
            <DataTable
              data={list(d?.recommendations).map((r: any, i: number) => ({
                ...r,
                id: r.id || r.unit?.id || String(i),
              }))}
              columns={[
                {
                  key: "project",
                  label: "Project",
                  render: (r) => r.project?.name,
                },
                {
                  key: "unit",
                  label: "Unit",
                  render: (r) => r.unit?.unitNumber,
                },
                { key: "reason", label: "Match context" },
              ]}
            />
            <h3 className="mt-6 mb-3">Visit history</h3>
            <DataTable
              data={list(d?.siteVisits)}
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
          </Async>
        </Modal>
      )}
    </>
  );
}
