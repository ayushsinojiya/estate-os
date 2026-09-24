import { useState } from "react";
import { Bell, Check, ShieldCheck } from "lucide-react";
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
  PageHeader,
  Pagination,
  useToast,
} from "../components/ui";
import { write } from "../api/client";
import { queryClient } from "../services/query";
import { date, label, list } from "../utils/format";
import type { Entity } from "../types";
export function Notifications() {
  const l = useList("/notifications");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const toast = useToast();
  return (
    <>
      <PageHeader
        title="Notifications"
        description="Appointments, assignments, and customer follow-ups, all in one place."
      />
      {error != null && <ErrorState error={error} />}
      <section className="panel">
        <Async query={l.query}>
          {list(l.query.data).length ? (
            list(l.query.data).map((n: Entity) => (
              <article
                className={`notification-row ${n.readAt || n.read ? "" : "unread"}`}
                key={n.id}
              >
                <div className="notification-icon">
                  <Bell size={20} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h3>{n.title || label(n.type)}</h3>
                    <Badge value={n.status || n.deliveryStatus} />
                    {n.mock && <Badge value="SIMULATED" />}
                  </div>
                  <p>{n.message || n.body}</p>
                  <small>
                    {date(n.createdAt)}
                    {n.audience === "CUSTOMER" ? " · Customer delivery" : ""}
                    {typeof n.recipient === "string" ? ` · ${n.recipient}` : ""}
                  </small>
                  {n.error && <p className="text-red-700 text-sm">{n.error}</p>}
                </div>
                {!(n.readAt || n.read) && (
                  <button
                    className="btn-secondary"
                    disabled={busy === n.id}
                    onClick={async () => {
                      setBusy(n.id);
                      setError(null);
                      try {
                        await write(`/notifications/${n.id}/read`, {});
                        await queryClient.invalidateQueries();
                        toast("Marked as read");
                      } catch (e) {
                        setError(e);
                      } finally {
                        setBusy("");
                      }
                    }}
                  >
                    <Check size={16} />
                    Mark read
                  </button>
                )}
              </article>
            ))
          ) : (
            <Empty
              title="You’re all caught up"
              description="Visit confirmations, assignments and reminders appear here."
            />
          )}
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
    </>
  );
}
export function Profile() {
  const { session, workspaceId } = useAuth();
  const q = useApi("/members");
  return (
    <>
      <PageHeader
        title="Profile & access"
        description="Your identity and membership in this workspace."
      />
      <div className="detail-columns">
        <section className="panel p-6">
          <div className="flex items-center gap-4 mb-6">
            <span className="avatar avatar-large">
              {session?.user.name?.slice(0, 2)}
            </span>
            <div>
              <h2>{session?.user.name}</h2>
              <p className="text-muted">{session?.user.email}</p>
            </div>
          </div>
          <Details
            data={{
              ...session?.user,
              workspace: session?.workspaces.find((w) => w.id === workspaceId)
                ?.name,
              role: label(
                session?.workspaces.find((w) => w.id === workspaceId)?.role,
              ),
            }}
            fields={["name", "email", "workspace", "role"]}
          />
          <p className="info-strip mt-6">
            <ShieldCheck size={18} />
            Identity and role changes are managed by your workspace
            administrator.
          </p>
        </section>
        <section className="panel p-6">
          <h2 className="mb-5">Workspace team</h2>
          <Async query={q}>
            {list(q.data).map((m: Entity) => (
              <div key={m.id} className="team-row">
                <span className="avatar">{m.name?.slice(0, 2)}</span>
                <div className="flex-1">
                  <strong>{m.name}</strong>
                  <small>{m.email}</small>
                </div>
                <Badge value={m.role} />
              </div>
            ))}
          </Async>
        </section>
      </div>
    </>
  );
}
export function AuditLogs() {
  const l = useList("/audit-logs");
  return (
    <>
      <PageHeader
        title="Audit trail"
        description="A traceable record of important workspace actions."
      />
      <section className="panel">
        <Filters {...l} statuses={[]} />
        <Async query={l.query}>
          <DataTable
            data={list(l.query.data)}
            columns={[
              {
                key: "createdAt",
                label: "Timestamp",
                render: (r) => date(r.createdAt || r.timestamp),
              },
              {
                key: "action",
                label: "Action",
                render: (r) => label(r.action),
              },
              { key: "entityType", label: "Entity" },
              { key: "entityId", label: "Record ID" },
              { key: "userId", label: "User" },
              {
                key: "metadata",
                label: "Context",
                render: (r) =>
                  typeof r.metadata === "object"
                    ? JSON.stringify(r.metadata)
                    : r.metadata || "—",
              },
            ]}
          />
          <Pagination data={l.query.data} page={l.page} setPage={l.setPage} />
        </Async>
      </section>
    </>
  );
}
