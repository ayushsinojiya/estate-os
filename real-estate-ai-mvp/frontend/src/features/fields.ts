import type { Entity, Field, RemoteOptions } from "../types";
import { date, languages, options } from "../utils/format";
export const leadOptions: RemoteOptions = {
  path: "/leads",
  detailPath: "/leads",
  label: (record) => `${record.name} · ${record.phone || record.email || ""}`,
};
export const projectOptions: RemoteOptions = {
  path: "/projects",
  detailPath: "/projects",
  label: (record) =>
    `${record.name}${record.location ? ` · ${record.location}` : ""}`,
};
export const availableUnitOptions: RemoteOptions = {
  path: (values) => `/projects/${values.projectId}/units?status=AVAILABLE`,
  detailPath: "/units",
  label: (record) =>
    `${record.unitNumber} · ${record.propertyType || "Unit"} · ${record.status}`,
};
export const appointmentOptions: RemoteOptions = {
  path: (values) =>
    `/site-visits?leadId=${encodeURIComponent(values.leadId || "")}&sort=scheduledAt,asc`,
  detailPath: "/site-visits",
  label: (record) =>
    `${date(record.scheduledAt)} · ${record.leadName || `Lead ${record.leadId}`} · ${record.status}`,
};
export const projectStatuses = ["ACTIVE", "INACTIVE", "COMPLETED", "ARCHIVED"];
export const leadStatuses = [
  "NEW",
  "CONTACTED",
  "QUALIFIED",
  "VISIT_PLANNED",
  "VISIT_COMPLETED",
  "HANDED_OVER",
  "NOT_INTERESTED",
  "LOST",
];
export const visitStatuses = [
  "REQUESTED",
  "CONFIRMED",
  "RESCHEDULED",
  "CANCELLED",
  "COMPLETED",
  "NO_SHOW",
];
export const unitStatuses = [
  "AVAILABLE",
  "RESERVED",
  "SOLD",
  "BLOCKED",
  "UNAVAILABLE",
];
export const entityOptions = (items: Entity[], key = "name") =>
  items.map((i) => ({ value: i.id, label: i[key] || i.unitNumber || i.id }));
export const projectFields: Field[] = [
  { name: "name", label: "Project name", required: true },
  { name: "developer", label: "Developer / builder", required: true },
  { name: "location", label: "Location", required: true },
  { name: "possessionDate", label: "Possession date", type: "date" },
  {
    name: "status",
    label: "Status",
    required: true,
    options: options(projectStatuses),
  },
  { name: "mediaUrl", label: "Image / media URL", type: "url" },
  { name: "description", label: "Description", type: "textarea", wide: true },
  {
    name: "amenities",
    label: "Amenities",
    wide: true,
    hint: "Separate amenities with commas.",
  },
];
export function leadFields(members: Entity[]): Field[] {
  return [
    { name: "name", label: "Full name", required: true },
    { name: "phone", label: "Phone", type: "tel", required: true },
    { name: "email", label: "Email", type: "email" },
    {
      name: "language",
      label: "Preferred language",
      required: true,
      options: languages,
    },
    {
      name: "status",
      label: "Lead status",
      required: true,
      options: options(leadStatuses),
    },
    {
      name: "source",
      label: "Source",
      required: true,
      options: options([
        "WEBSITE",
        "PHONE",
        "REFERRAL",
        "WALK_IN",
        "CAMPAIGN",
        "OTHER",
      ]),
    },
    {
      name: "assignedAgentId",
      label: "Assigned agent",
      options: entityOptions(
        members.filter((m) => m.role === "REAL_ESTATE_AGENT"),
      ),
    },
    {
      name: "intent",
      label: "Intent",
      required: true,
      options: options(["BUY", "RENT"]),
    },
    { name: "budgetMin", label: "Minimum budget (₹)", type: "number", min: 0 },
    { name: "budgetMax", label: "Maximum budget (₹)", type: "number", min: 0 },
    { name: "location", label: "Preferred location" },
    {
      name: "propertyType",
      label: "Property type",
      options: options(["APARTMENT", "VILLA", "PLOT", "COMMERCIAL"]),
    },
    { name: "bhk", label: "Bedrooms / BHK", type: "number", min: 0, step: "1" },
    { name: "areaMin", label: "Minimum area (sq ft)", type: "number", min: 0 },
    { name: "areaMax", label: "Maximum area (sq ft)", type: "number", min: 0 },
    { name: "possessionTimeline", label: "Possession timeline" },
    {
      name: "purpose",
      label: "Purpose",
      options: options(["SELF_USE", "INVESTMENT", "OTHER"]),
    },
    {
      name: "urgency",
      label: "Urgency",
      options: options(["LOW", "MEDIUM", "HIGH"]),
    },
    { name: "followUpAt", label: "Next follow-up", type: "datetime-local" },
    { name: "tags", label: "Tags", hint: "Separate tags with commas." },
    {
      name: "notes",
      label: "Customer requirements & notes",
      type: "textarea",
      wide: true,
    },
  ];
}
export function unitFields(
  buildings: Entity[],
  floors: Entity[] = [],
  types: Entity[] = [],
): Field[] {
  return [
    {
      name: "buildingId",
      label: "Building / tower",
      required: true,
      options: entityOptions(buildings),
    },
    { name: "unitNumber", label: "Unit number", required: true },
    {
      name: "floorId",
      label: "Catalog floor",
      dependsOn: "buildingId",
      options: floors.map((f) => ({
        value: f.id,
        label: `Floor ${f.number}`,
        parentValue: f.buildingId,
      })),
      hint: "Choose a floor from this building. Its floor number is used automatically.",
    },
    {
      name: "unitTypeId",
      label: "Catalog unit type",
      options: entityOptions(types),
    },
    {
      name: "propertyType",
      label: "Property type",
      required: true,
      options: options(["APARTMENT", "VILLA", "PLOT", "COMMERCIAL"]),
    },
    {
      name: "bhk",
      label: "Bedrooms / BHK",
      type: "number",
      required: true,
      min: 0,
      step: "1",
    },
    {
      name: "area",
      label: "Area (sq ft)",
      type: "number",
      required: true,
      min: 1,
    },
    {
      name: "floor",
      label: "Floor number (without catalog selection)",
      type: "number",
      step: "1",
    },
    {
      name: "facing",
      label: "Facing",
      options: options([
        "NORTH",
        "SOUTH",
        "EAST",
        "WEST",
        "NORTH_EAST",
        "NORTH_WEST",
        "SOUTH_EAST",
        "SOUTH_WEST",
      ]),
    },
    {
      name: "price",
      label: "Price (₹)",
      type: "number",
      required: true,
      min: 1,
    },
    {
      name: "status",
      label: "Availability",
      required: true,
      options: options(unitStatuses),
    },
  ];
}
export const documentFields: Field[] = [
  { name: "title", label: "Document title", required: true },
  {
    name: "fileName",
    label: "Original PDF filename",
    required: true,
    hint: "Register the PDF already stored in your file storage service.",
  },
  {
    name: "storageReference",
    label: "Storage reference",
    required: true,
    wide: true,
    hint: "A stable storage key or URL of the original PDF. Original bytes remain in your configured storage service.",
  },
  { name: "language", label: "Language", required: true, options: languages },
  { name: "pageReference", label: "Page / section reference" },
  {
    name: "content",
    label: "Readable property content",
    type: "textarea",
    wide: true,
    required: true,
  },
];
export function visitFields(
  leads: Entity[],
  projects: Entity[],
  members: Entity[],
  units: Entity[],
): Field[] {
  return [
    {
      name: "leadId",
      label: "Lead",
      required: true,
      options: entityOptions(leads),
    },
    {
      name: "projectId",
      label: "Project",
      required: true,
      options: entityOptions(projects),
    },
    {
      name: "unitId",
      label: "Unit (optional)",
      dependsOn: "projectId",
      options: units.map((u) => ({
        value: u.id,
        parentValue: u.projectId,
        label: `${u.unitNumber} · ${u.projectName || u.propertyType} · ${u.status}`,
      })),
      hint: "Select a project first. Only its currently available units are shown.",
    },
    {
      name: "agentId",
      label: "Assigned agent",
      required: true,
      options: entityOptions(
        members.filter((m) => m.role === "REAL_ESTATE_AGENT"),
      ),
    },
    {
      name: "scheduledAt",
      label: "Date & time",
      required: true,
      type: "datetime-local",
      hint: "Shown in your local timezone; stored securely in UTC.",
    },
    {
      name: "durationMinutes",
      label: "Duration (minutes)",
      type: "number",
      required: true,
      min: 15,
      max: 240,
      step: "15",
    },
    {
      name: "confirmationStatus",
      label: "Customer confirmation",
      options: options(["PENDING", "CONFIRMED", "DECLINED"]),
      hint: "Record the customer's response; notification delivery is tracked separately.",
    },
    {
      name: "status",
      label: "Visit status",
      options: options(visitStatuses),
      required: true,
    },
    { name: "notes", label: "Visit notes", type: "textarea", wide: true },
  ];
}
