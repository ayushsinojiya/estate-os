import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, write } from "../api/client";
import { Async, Badge, DataTable, Details, ErrorState, Modal, RecordForm, useToast } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { queryClient } from "../services/query";
import type { Entity } from "../types";
import { date, label, list } from "../utils/format";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type SlotWindow = { days: number[]; start: string; end: string; slotMinutes: number; capacity: number };

/** Visits booked by the voice agent carry bookedBy=VOICE_AGENT; flagged ones need a manager. */
export function VisitBadges({ visit }: { visit: Entity }) {
  return (
    <>
      {visit.bookedBy === "VOICE_AGENT" && <Badge value="Booked by Riya" />}
      {visit.needsManagerReview && <Badge value="NEEDS_REVIEW" />}
    </>
  );
}

/** Weekly visiting hours for one project (ADMIN/MANAGER edit), with the next free slots. */
export function VisitingHours({ projectId }: { projectId: string }) {
  const { canManage } = useAuth();
  const templates = useApi(`/projects/${projectId}/visit-slots`, !!projectId);
  const slots = useApi(`/projects/${projectId}/slots?days=3`, !!projectId);
  const [windows, setWindows] = useState<SlotWindow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  useEffect(() => {
    if (templates.data?.windows)
      setWindows(templates.data.windows.map((w: SlotWindow) => ({ ...w, start: w.start.slice(0, 5), end: w.end.slice(0, 5) })));
  }, [templates.data]);
  const update = (index: number, patch: Partial<SlotWindow>) =>
    setWindows((current) => current.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  async function save() {
    setSaving(true);
    setError(null);
    try {
      await write(`/projects/${projectId}/visit-slots`, { windows }, "PUT");
      await queryClient.invalidateQueries();
      toast("Visiting hours saved");
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Async query={templates}>
      <p className="text-muted mb-4">
        {templates.data?.source === "PROJECT"
          ? "This project has its own visiting hours."
          : templates.data?.source === "WORKSPACE"
            ? "Using the workspace's default visiting hours. Saving creates hours for this project only."
            : "Using the standard hours (every day 10:00–19:00, 60-minute visits, 3 at a time)."}{" "}
        Times are India Standard Time. Riya offers these slots on calls; a full slot is never offered.
      </p>
      {error != null && <ErrorState error={error} />}
      <div className="space-y-3">
        {windows.map((w, index) => (
          <fieldset key={index} className="rounded border p-3 flex flex-wrap gap-3 items-end" disabled={!canManage}>
            <legend className="sr-only">Visiting window {index + 1}</legend>
            <div className="flex gap-1 flex-wrap" role="group" aria-label="Days">
              {DAYS.map((day, d) => (
                <label key={day} className="flex items-center gap-1 text-sm">
                  <input
                    type="checkbox"
                    checked={w.days.includes(d + 1)}
                    onChange={(e) =>
                      update(index, {
                        days: e.target.checked ? [...w.days, d + 1].sort() : w.days.filter((x) => x !== d + 1),
                      })
                    }
                  />
                  {day}
                </label>
              ))}
            </div>
            <label className="text-sm">From <input type="time" value={w.start} onChange={(e) => update(index, { start: e.target.value })} /></label>
            <label className="text-sm">To <input type="time" value={w.end} onChange={(e) => update(index, { end: e.target.value })} /></label>
            <label className="text-sm">Visit length (min)
              <input type="number" min={15} max={240} step={15} value={w.slotMinutes} onChange={(e) => update(index, { slotMinutes: Number(e.target.value) })} />
            </label>
            <label className="text-sm">Visits at a time
              <input type="number" min={1} max={100} value={w.capacity} onChange={(e) => update(index, { capacity: Number(e.target.value) })} />
            </label>
            {canManage && windows.length > 1 && (
              <button type="button" className="btn-secondary" onClick={() => setWindows(windows.filter((_, i) => i !== index))}>
                Remove
              </button>
            )}
          </fieldset>
        ))}
      </div>
      {canManage && (
        <div className="flex gap-3 mt-4">
          <button type="button" className="btn-secondary"
            onClick={() => setWindows([...windows, { days: [6, 7], start: "10:00", end: "19:00", slotMinutes: 60, capacity: 3 }])}>
            Add window
          </button>
          <button type="button" className="btn-primary" disabled={saving || !windows.length} onClick={() => void save()}>
            {saving ? "Saving…" : "Save visiting hours"}
          </button>
        </div>
      )}
      <h3 className="font-semibold mt-6 mb-2">Next free slots</h3>
      <Async query={slots}>
        {list(slots.data?.slots).length ? (
          <div className="flex flex-wrap gap-2">
            {list(slots.data?.slots).slice(0, 12).map((s: Entity) => (
              <span key={s.start} className="badge badge-neutral" title={s.startLocal}>
                {s.label} · {s.remaining} left
              </span>
            ))}
          </div>
        ) : (
          <p className="text-muted">No free slots in the next three days.</p>
        )}
      </Async>
    </Async>
  );
}

/** Which sales agents take visits for a project; round-robin assignment uses this list. */
export function ProjectAgents({ projectId }: { projectId: string }) {
  const { canManage } = useAuth();
  const assigned = useApi(`/projects/${projectId}/agents`, !!projectId);
  const members = useApi("/members");
  const [edit, setEdit] = useState(false);
  const toast = useToast();
  const agents = list(members.data).filter((m: Entity) => m.role === "REAL_ESTATE_AGENT");
  return (
    <section className="panel">
      <div className="panel-heading flex justify-between items-center">
        <h2>Assigned agents</h2>
        {canManage && (
          <button className="btn-secondary" onClick={() => setEdit(true)}>
            Manage agents
          </button>
        )}
      </div>
      <Async query={assigned}>
        <DataTable
          data={list(assigned.data).map((a: Entity) => ({ ...a, id: a.userId }))}
          empty="No agents assigned: visits rotate across every available agent in the workspace."
          columns={[
            { key: "name", label: "Agent" },
            { key: "phone", label: "Phone", render: (a) => a.phone || "—" },
            {
              key: "available",
              label: "Takes visits",
              render: (a) => <Badge value={a.available && a.agentAvailable ? "AVAILABLE" : "UNAVAILABLE"} />,
            },
            { key: "lastAssignedAt", label: "Last assigned", render: (a) => (a.lastAssignedAt ? date(a.lastAssignedAt) : "Never") },
          ]}
        />
      </Async>
      {edit && (
        <Modal title="Agents for this project" onClose={() => setEdit(false)}>
          <RecordForm
            fields={agents.map((a: Entity) => ({
              name: `agent_${a.id}`,
              label: a.name,
              options: [
                { value: "true", label: "Takes visits for this project" },
                { value: "false", label: "Not on this project" },
              ],
            }))}
            initial={Object.fromEntries(
              agents.map((a: Entity) => [
                `agent_${a.id}`,
                list(assigned.data).some((x: Entity) => x.userId === a.id && x.available) ? "true" : "false",
              ]),
            )}
            submitLabel="Save agents"
            onCancel={() => setEdit(false)}
            onSubmit={async (data) => {
              const chosen = agents.filter((a: Entity) => data[`agent_${a.id}`] === "true");
              await write(`/projects/${projectId}/agents`, { agents: chosen.map((a: Entity) => ({ userId: a.id, available: true })) }, "PUT");
              await queryClient.invalidateQueries();
              setEdit(false);
              toast("Project agents saved");
            }}
          />
        </Modal>
      )}
    </section>
  );
}

/** Shown on a lead the CRM must not call. */
export function DncBanner({ lead }: { lead: Entity }) {
  if (!lead.dnc && !lead.doNotCall) return null;
  return (
    <div role="alert" className="error-state mb-4">
      <div>
        <h3>Do not call</h3>
        <p>
          This number is on the do-not-call list{lead.doNotCallBasis ? ` (${lead.doNotCallBasis})` : ""}. Outbound calls,
          reminders and callbacks are blocked.
        </p>
      </div>
    </div>
  );
}

export function MarkDnc({ lead, children }: { lead: Entity; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  if (lead.dnc) return null;
  return (
    <>
      <button className="btn-secondary" onClick={() => setOpen(true)}>
        {children || "Do not call"}
      </button>
      {open && (
        <Modal title="Add this number to the do-not-call list?" onClose={() => setOpen(false)}>
          <RecordForm
            fields={[{ name: "reason", label: "Reason", wide: true }]}
            submitLabel="Add to do-not-call list"
            onCancel={() => setOpen(false)}
            onSubmit={async (data) => {
              await write("/dnc", { phone: lead.phone, reason: data.reason || "Customer request", leadId: lead.id });
              await queryClient.invalidateQueries();
              setOpen(false);
              toast("Number added to the do-not-call list");
            }}
          />
        </Modal>
      )}
    </>
  );
}

/** Callbacks for a lead, and the outbound calls the CRM has scheduled for it. */
export function LeadCallbacks({ lead }: { lead: Entity }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [cancelCallback, setCancelCallback] = useState<Entity | null>(null);
  return (
    <section className="panel">
      <div className="panel-heading flex justify-between items-center">
        <h2>Callbacks & scheduled calls</h2>
        {!lead.dnc && (
          <button className="btn-secondary" onClick={() => setOpen(true)}>
            Schedule callback
          </button>
        )}
      </div>
      <DataTable
        data={list(lead.callbacks)}
        empty="No callbacks requested."
        columns={[
          { key: "dueAt", label: "Due", render: (c) => date(c.dueAt) },
          { key: "requestedBy", label: "Requested by", render: (c) => label(c.requestedBy) },
          { key: "reason", label: "Reason", render: (c) => c.reason || "—" },
          { key: "status", label: "Status", render: (c) => <Badge value={c.status} /> },
        ]}
        actions={(c) =>
          c.status === "SCHEDULED" ? (
            <button className="text-link" onClick={() => setCancelCallback(c)}>
              Cancel
            </button>
          ) : null
        }
      />
      {list(lead.scheduledCalls).length > 0 && (
        <div className="p-5 border-t space-y-2">
          {list(lead.scheduledCalls).map((s: Entity) => (
            <div key={s.id} className="flex justify-between gap-3">
              <span>
                {label(s.callType)} · {date(s.dueAt)}
                {s.deferredReason ? ` · deferred (${label(s.deferredReason)})` : ""}
                {s.skipReason ? ` · ${label(s.skipReason)}` : ""}
              </span>
              <Badge value={s.status} />
            </div>
          ))}
        </div>
      )}
      {open && (
        <Modal title="Schedule a callback" onClose={() => setOpen(false)}>
          <RecordForm
            fields={[
              { name: "dueAt", label: "Call back at", type: "datetime-local", required: true },
              { name: "reason", label: "Reason", wide: true },
            ]}
            submitLabel="Schedule callback"
            onCancel={() => setOpen(false)}
            onSubmit={async (data) => {
              await write(`/leads/${lead.id}/callbacks`, { dueAt: data.dueAt, reason: data.reason || null });
              await queryClient.invalidateQueries();
              setOpen(false);
              toast("Callback scheduled; calls outside 09:00–21:00 IST move to the next morning");
            }}
          />
        </Modal>
      )}
      {cancelCallback && (
        <Modal title="Cancel callback?" onClose={() => setCancelCallback(null)}>
          <p className="text-muted mb-5">
            The callback due {date(cancelCallback.dueAt)} will no longer be scheduled.
          </p>
          <RecordForm
            fields={[]}
            submitLabel="Confirm cancellation"
            danger
            onCancel={() => setCancelCallback(null)}
            onSubmit={async () => {
              await write(`/callbacks/${cancelCallback.id}/cancel`, {});
              await queryClient.invalidateQueries();
              setCancelCallback(null);
              toast("Callback cancelled");
            }}
          />
        </Modal>
      )}
    </section>
  );
}

/** What the voice agent recorded about a call beyond the transcript. */
export function CallOutcome({ call }: { call: Entity }) {
  const fields = [
    "callType",
    "leadTemperature",
    "leadScore",
    "visitOutcome",
    "handoverRequested",
    "handoverReason",
    "callbackAt",
    "whatsappConsent",
    "whatsappRequests",
    "purpose",
    "possessionPreference",
    "promptVersion",
  ].filter((f) => call[f] != null && call[f] !== "");
  const questions = list(call.unansweredQuestions);
  const citations = list(call.citations);
  if (!fields.length && !questions.length && !citations.length) return null;
  return (
    <section className="panel p-6">
      <h2 className="mb-5">Call outcome</h2>
      <Details data={call} fields={fields} />
      {questions.length > 0 && (
        <div className="mt-4">
          <h3 className="font-semibold mb-2">Questions for a person</h3>
          <ul className="list-disc ml-5">
            {questions.map((q: string) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      )}
      {citations.length > 0 && (
        <p className="text-muted mt-4">Knowledge used: {citations.map((c: string) => `#${c}`).join(", ")}</p>
      )}
      {call.outcomes && <p className="text-muted mt-2">Recorded: {Object.keys(call.outcomes).map(label).join(", ")}</p>}
    </section>
  );
}

/** Keeps in-flight document statuses current: asks the CRM to re-check each one every few seconds. */
export function useProcessingPoll(documents: Entity[]) {
  const inFlight = documents.filter((d) => ["UPLOADED", "PARSING", "EMBEDDING", "QUEUED", "PENDING_INDEX"].includes(d.processingStatus));
  const key = inFlight.map((d) => d.id).join(",");
  useEffect(() => {
    if (!key) return;
    const timer = setInterval(async () => {
      await Promise.allSettled(key.split(",").map((id) => api(`/documents/${id}/processing-status`)));
      await queryClient.invalidateQueries();
    }, 5000);
    return () => clearInterval(timer);
  }, [key]);
}
