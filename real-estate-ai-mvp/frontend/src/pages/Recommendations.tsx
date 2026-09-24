import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Building2, Check, Sparkles } from "lucide-react";
import {
  Badge,
  Empty,
  ErrorState,
  PageHeader,
  RecordForm,
  useToast,
} from "../components/ui";
import { write } from "../api/client";
import { queryClient } from "../services/query";
import { leadOptions, projectOptions } from "../features/fields";
import { AsyncSelect } from "../components/AsyncSelect";
import { languages, list, money, options } from "../utils/format";
import { RichContent } from "./Calls";
export function Recommendations() {
  const [params] = useSearchParams();
  const [result, setResult] = useState<any>(null);
  const [leadId, setLeadId] = useState(params.get("leadId") || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  return (
    <>
      <PageHeader
        title="Find their right place"
        description="Match real requirements to available properties, with context from published knowledge."
      />
      <div className="recommendation-layout">
        <section className="panel p-6 h-fit">
          <div className="flex gap-2 items-center mb-5">
            <Sparkles size={19} className="text-brand-600" />
            <h2>Customer preferences</h2>
          </div>
          <RecordForm
            submitLabel="Find matching properties"
            initial={{ leadId: params.get("leadId") || "", language: "en" }}
            fields={[
              {
                name: "leadId",
                label: "Use saved lead preferences",
                remote: leadOptions,
                wide: true,
                hint: "Select a lead to use saved requirements; optional fields below refine the search.",
              },
              {
                name: "projectId",
                label: "Project (optional)",
                remote: projectOptions,
                wide: true,
              },
              {
                name: "budgetMin",
                label: "Minimum budget (₹)",
                type: "number",
                min: 0,
              },
              {
                name: "budgetMax",
                label: "Maximum budget (₹)",
                type: "number",
                min: 0,
              },
              { name: "location", label: "Location" },
              { name: "bhk", label: "BHK", type: "number", min: 0, step: "1" },
              {
                name: "propertyType",
                label: "Property type",
                options: options(["APARTMENT", "VILLA", "PLOT", "COMMERCIAL"]),
              },
              {
                name: "language",
                label: "Knowledge language",
                options: languages,
              },
              {
                name: "areaMin",
                label: "Minimum area (sq ft)",
                type: "number",
                min: 0,
              },
              {
                name: "areaMax",
                label: "Maximum area (sq ft)",
                type: "number",
                min: 0,
              },
              {
                name: "query",
                label: "What else matters?",
                type: "textarea",
                wide: true,
                hint: "For example: a gym, possession timeline, or nearby schools.",
              },
            ]}
            onSubmit={async (data) => {
              const r = await write("/recommendations/search", data);
              setResult(r);
              setLeadId(data.leadId || "");
              setSelected([]);
            }}
          />
        </section>
        <div className="space-y-5">
          {result == null ? (
            <section className="panel">
              <Empty
                title="Good matches start with understanding"
                description="Select a lead or enter preferences to search available inventory and published property knowledge."
              />
            </section>
          ) : (
            <>
              {result.mock && (
                <div className="demo-strip">
                  <strong>Demo knowledge adapter</strong>
                  <span>
                    Inventory matches use stored availability. Live document
                    retrieval is unavailable in demo mode.
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center">
                <h2>{list(result).length} matching properties</h2>
                <Badge value="AVAILABLE INVENTORY" />
              </div>
              {!list(result).length && (
                <section className="panel">
                  <Empty
                    title="No matching properties"
                    description="Broaden the budget, location, or area range and try again."
                  />
                </section>
              )}
              {list(result).map((r: any) => {
                const u = r.unit || r,
                  p = r.project || {};
                return (
                  <article className="match-card panel" key={u.id}>
                    <div className="match-icon">
                      <Building2 size={28} />
                    </div>
                    <div className="flex-1">
                      <div className="flex justify-between flex-wrap gap-2">
                        <div>
                          <span className="eyebrow">{p.location}</span>
                          <h2>
                            {p.name || "Matching property"} · {u.unitNumber}
                          </h2>
                        </div>
                        <strong className="text-xl">{money(u.price)}</strong>
                      </div>
                      <p className="text-muted mt-2">
                        {u.bhk} BHK · {u.area} sq ft · Floor {u.floor} ·{" "}
                        {u.facing}
                      </p>
                      <p className="match-reason">
                        <Check size={15} />
                        {r.reason}
                      </p>
                      <div className="flex items-center justify-between gap-3 mt-4">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={selected.includes(u.id)}
                            onChange={(e) =>
                              setSelected(
                                e.target.checked
                                  ? [...selected, u.id]
                                  : selected.filter((i) => i !== u.id),
                              )
                            }
                          />
                          Select for this lead
                        </label>
                        <Link
                          className="text-link"
                          to={`/projects/${p.id || u.projectId}`}
                        >
                          View project →
                        </Link>
                      </div>
                    </div>
                  </article>
                );
              })}
              {selected.length > 0 && (
                <div className="panel p-5">
                  {error != null && <ErrorState error={error} />}
                  <label className="field-label" htmlFor="saveLead">
                    Record suggestions for
                  </label>
                  <div className="flex gap-3">
                    <AsyncSelect
                      id="saveLead"
                      label="Lead to receive suggestions"
                      value={leadId}
                      onChange={setLeadId}
                      remote={leadOptions}
                      disabled={saving}
                    />
                    <button
                      className="btn-primary whitespace-nowrap"
                      disabled={!leadId || saving}
                      onClick={async () => {
                        setSaving(true);
                        setError(null);
                        try {
                          await write(`/leads/${leadId}/recommendations`, {
                            unitIds: selected,
                          });
                          await queryClient.invalidateQueries();
                          toast(
                            `${selected.length} property suggestions saved`,
                          );
                        } catch (e) {
                          setError(e);
                        } finally {
                          setSaving(false);
                        }
                      }}
                    >
                      Save {selected.length} suggestions
                    </button>
                  </div>
                  {leadId && (
                    <Link
                      className="text-link mt-4"
                      to={`/site-visits?create=true&leadId=${leadId}`}
                    >
                      Continue to site-visit booking →
                    </Link>
                  )}
                </div>
              )}
              {result.knowledge && (
                <section className="panel p-6">
                  <h2 className="mb-4">Published property knowledge</h2>
                  <RichContent value={result.knowledge} />
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
