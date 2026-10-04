import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "../src/services/query";
import { AuthProvider } from "../src/hooks/useAuth";
import { Filters, ToastProvider, RecordForm } from "../src/components/ui";
import { AsyncSelect } from "../src/components/AsyncSelect";
import { DateTimePicker } from "../src/components/DateTimePicker";
import { App } from "../src/routes/App";
import { money } from "../src/utils/format";
import { visitFields, leadOptions, unitFields } from "../src/features/fields";
const session = {
  token: "test-token",
  user: { id: "1", name: "Anaya Shah", email: "admin@estraos.demo" },
  workspaces: [{ id: "1", name: "Demo workspace", role: "ADMIN" }],
};
const lead = {
  id: "11",
  name: "Riya Patel",
  phone: "9876543210",
  email: "riya@example.com",
  language: "en",
  status: "NEW",
  source: "WEBSITE",
  intent: "BUY",
  budgetMax: 9000000,
};
const project = {
  id: "21",
  name: "The Green Residences",
  location: "Ahmedabad",
  developer: "Green Homes",
  status: "ACTIVE",
};
const agent = { id: "3", name: "Dev Mehta", role: "REAL_ESTATE_AGENT" };
let fetchMock: ReturnType<typeof vi.fn>;
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mount(path: string, authenticated = true) {
  if (authenticated) {
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}
async function chooseOption(user: ReturnType<typeof userEvent.setup>, label: RegExp | string, option: RegExp | string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(screen.getByRole("option", { name: option }));
}
beforeEach(() => {
  queryClient.clear();
  queryClient.setDefaultOptions({
    queries: { retry: false, staleTime: Infinity },
  });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace("/api/v1", "").split("?")[0];
    if (path === "/auth/me" || path === "/auth/login") return json(session);
    if (path === "/members") return json([agent]);
    if (path === "/dashboard")
      return json({
        demo: true,
        metrics: { totalLeads: 1 },
        recentActivities: [],
        upcomingVisits: [],
        followUps: [],
      });
    if (path === "/leads/11")
      return json({
        ...lead,
        ...(init?.body ? JSON.parse(String(init.body)) : {}),
        activities: [],
        notesHistory: [],
      });
    if (path === "/leads" && init?.method === "POST")
      return json({ ...lead, ...JSON.parse(String(init.body)) });
    if (path === "/leads")
      return json({ items: [lead], total: 1, page: 0, size: 10 });
    if (path === "/projects")
      return json({ items: [project], total: 1, page: 0, size: 10 });
    if (path === "/site-visits" && init?.method === "POST")
      return json({ id: "31", ...JSON.parse(String(init.body)) });
    if (path === "/site-visits/31")
      return json({
        id: "31",
        leadId: "11",
        projectId: "21",
        agentId: "3",
        scheduledAt: "2030-10-12T10:00:00Z",
        durationMinutes: 60,
        status: "CONFIRMED",
      });
    return json({ items: [], total: 0, page: 0, size: 10 });
  });
  vi.stubGlobal("fetch", fetchMock);
});
describe("authenticated workspace flows", () => {
  it("shows a workspace file history with upload controls", async () => {
    mount("/files");
    expect(await screen.findByRole("heading", { name: "File management" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload files" })).toBeInTheDocument();
  });
  it("places the workspace switcher in the header", async () => {
    mount("/dashboard");

    expect(await screen.findByRole("combobox", { name: "Connected workspace" })).toHaveTextContent(
      "Demo workspace",
    );
    expect(screen.queryByRole("combobox", { name: "Your workspace" })).not.toBeInTheDocument();
  });
  it("protects workspace routes from unauthenticated visitors", async () => {
    mount("/projects", false);
    expect(
      await screen.findByRole("heading", { name: "Let’s get you settled in." }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("restores an authenticated session shared with a new tab", async () => {
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");

    mount("/dashboard", false);

    expect(await screen.findByRole("heading", { name: /Good to see you/ })).toBeInTheDocument();
  });
  it("signs in and sends the returned workspace context on API calls", async () => {
    const user = userEvent.setup();
    mount("/login", false);
    await user.type(screen.getByLabelText("Work email"), "admin@estraos.demo");
    await user.type(screen.getByLabelText("Password"), "example-test-password");
    await user.click(
      screen.getByRole("button", { name: "Sign in to workspace" }),
    );
    expect(
      await screen.findByRole("heading", { name: /Good to see you/ }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/dashboard",
        expect.objectContaining({
          headers: expect.objectContaining({
            "X-Workspace-Id": "1",
            Authorization: "Bearer test-token",
          }),
        }),
      ),
    );
  });
  it("renders project API results and does not expose management controls to agents", async () => {
    session.workspaces[0].role = "REAL_ESTATE_AGENT";
    mount("/projects");
    expect(
      await screen.findByRole("heading", { name: /The Green Residences/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "New project" }),
    ).not.toBeInTheDocument();
    session.workspaces[0].role = "ADMIN";
  });
  it("creates a lead using validated fields and opens the saved record", async () => {
    const user = userEvent.setup();
    mount("/leads");
    await screen.findByText("Riya Patel");
    await user.click(screen.getByRole("button", { name: "Add lead" }));
    await user.type(screen.getByLabelText(/Full name/), "Nisha Shah");
    await user.type(screen.getByLabelText(/^Phone/), "9123456789");
    await user.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/leads",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Nisha Shah"),
        }),
      ),
    );
    expect(
      await screen.findByRole("heading", { name: "Customer requirements" }),
    ).toBeInTheDocument();
  });
  it("updates an existing lead", async () => {
    const user = userEvent.setup();
    mount("/leads/11");
    await screen.findByRole("heading", { name: "Riya Patel" });
    await user.click(screen.getByRole("button", { name: "Edit lead" }));
    const field = screen.getByLabelText(/Full name/);
    await user.clear(field);
    await user.type(field, "Riya Patel Updated");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/leads/11",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining("Riya Patel Updated"),
        }),
      ),
    );
  });
  it("books a site visit with lead, project, agent and UTC time", async () => {
    const user = userEvent.setup();
    mount("/site-visits?create=true&leadId=11");
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("combobox", { name: "Project" }));
    await user.click(
      await screen.findByRole("option", { name: /The Green Residences/ }),
    );
    await chooseOption(user, /^Assigned agent/, /Dev Mehta/);
    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await user.click(screen.getAllByRole("button", { name: /^\d+ \w+ \d{4}$/ })[0]);
    await user.click(screen.getByRole("button", { name: "Confirm booking" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/site-visits",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"agentId":"3"'),
        }),
      ),
    );
    expect(
      await screen.findByRole("heading", { name: "Site visit details" }),
    ).toBeInTheDocument();
  });
  it("changes a visit status without posting response-only fields", async () => {
    const user = userEvent.setup();
    mount("/site-visits/31");

    await user.click(await screen.findByRole("button", { name: "Mark completed" }));
    await user.click(screen.getByRole("button", { name: "Confirm status change" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/site-visits/31",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const [, request] = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/v1/site-visits/31" && init?.method === "PUT",
    )!;
    expect(JSON.parse(String(request.body))).toEqual({
      leadId: "11",
      projectId: "21",
      unitId: null,
      agentId: "3",
      scheduledAt: "2030-10-12T10:00:00Z",
      durationMinutes: 60,
      notes: null,
      status: "COMPLETED",
    });
  });
  it("shows a recoverable API error", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/auth/me")
        ? json(session)
        : json({ message: "Workspace service unavailable" }, 503),
    );
    mount("/projects");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Workspace service unavailable",
    );
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
  it("shows loading while a workspace request is pending", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/auth/me") ? json(session) : new Promise(() => {}),
    );
    mount("/projects");
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "Loading" }),
      ).toBeInTheDocument(),
    );
  });
});
describe("form validation", () => {
  it("limits catalog floors to the selected building and clears them when changed", async () => {
    const user = userEvent.setup();
    render(
      <RecordForm
        fields={unitFields(
          [
            { id: "1", name: "Tower A" },
            { id: "2", name: "Tower B" },
          ],
          [
            { id: "10", number: 3, buildingId: "1" },
            { id: "20", number: 4, buildingId: "2" },
          ],
          [{ id: "30", name: "Corner apartment" }],
        ).filter((f) =>
          ["buildingId", "floorId", "unitTypeId"].includes(f.name),
        )}
        onSubmit={vi.fn()}
      />,
    );
    await chooseOption(user, "Building / tower", /Tower A/);
    await chooseOption(user, "Catalog floor", /Floor 3/);
    await user.click(screen.getByRole("combobox", { name: "Catalog floor" }));
    expect(
      screen.queryByRole("option", { name: "Floor 4" }),
    ).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await chooseOption(user, "Building / tower", /Tower B/);
    expect(screen.getByRole("combobox", { name: "Catalog floor" })).toHaveTextContent("Select catalog floor");
    await user.click(screen.getByRole("combobox", { name: "Catalog floor" }));
    expect(screen.getByRole("option", { name: "Floor 4" })).toBeInTheDocument();
  });
  it("shows selected property, agent and full requirements in a handover", async () => {
    const user = userEvent.setup();
    const original = fetchMock.getMockImplementation() as (
      url: string,
      init?: RequestInit,
    ) => Promise<Response>;
    const handover = {
      id: "81",
      leadId: "11",
      leadName: "Riya Patel",
      agentId: "3",
      status: "ASSIGNED",
      projectId: "21",
      unitId: "42",
      handoverAt: "2030-10-12T10:00:00Z",
      updatedAt: "2030-10-13T10:00:00Z",
      lead: {
        ...lead,
        areaMin: 1250,
        areaMax: 1800,
        possessionTimeline: "Within six months",
        purpose: "SELF_USE",
      },
      project,
      unit: { id: "42", unitNumber: "C-404", area: 1500 },
      agent: { name: "Dev Mehta" },
    };
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes("/handovers/81")) return json(handover);
      if (url.includes("/handovers?"))
        return json({ items: [handover], total: 1, page: 0, size: 10 });
      return original(url, init);
    });
    mount("/handovers");
    await user.click(await screen.findByRole("button", { name: "Riya Patel" }));
    expect(
      await screen.findByText("Assigned agent & selected property"),
    ).toBeInTheDocument();
    expect(screen.getByText("C-404")).toBeInTheDocument();
    expect(screen.getByText("Within six months")).toBeInTheDocument();
    expect(screen.getByText("1250")).toBeInTheDocument();
  });
  it("pages and searches remote options while preserving a saved selection", async () => {
    const user = userEvent.setup();
    const original = fetchMock.getMockImplementation() as (
      url: string,
      init?: RequestInit,
    ) => Promise<Response>;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes("/leads/999"))
        return json({ id: "999", name: "Saved distant lead" });
      if (url.includes("/leads?")) {
        const second = url.includes("page=1") || url.includes("search=Beyond");
        return json({
          items: [
            {
              id: second ? "101" : "1",
              name: second ? "Beyond first hundred" : "First lead",
            },
          ],
          total: 121,
          page: second ? 1 : 0,
          size: 20,
        });
      }
      return original(url, init);
    });
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RecordForm
            fields={[
              { name: "leadId", label: "Customer", remote: leadOptions },
            ]}
            initial={{ leadId: "999" }}
            onSubmit={vi.fn()}
          />
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Saved distant lead/)).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Customer" }));
    await user.click(
      screen.getByRole("button", { name: "Next customer options" }),
    );
    expect(
      await screen.findByRole("option", { name: /Beyond first hundred/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Customer" })).toHaveTextContent(
      "Saved distant lead",
    );
    await user.type(
      screen.getByRole("textbox", { name: "Search customer options" }),
      "Beyond",
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("page=0&size=20&search=Beyond"),
        expect.anything(),
      ),
    );
  });
  it("uses one searchable combobox for remote choices", async () => {
    const user = userEvent.setup();
    const selected = vi.fn();
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AsyncSelect
            id="customer"
            label="Customer"
            value=""
            onChange={selected}
            remote={leadOptions}
          />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("combobox", { name: "Customer" }));
    const search = screen.getByRole("textbox", {
      name: "Search customer options",
    });
    await user.type(search, "Riya");
    expect(search).toHaveAttribute("aria-controls", "customer-options");
    expect(search).toHaveAttribute("aria-activedescendant", "customer-option-0");
    expect(await screen.findByRole("option", { name: /Riya Patel/ })).toHaveAttribute(
      "id",
      "customer-option-0",
    );
    await user.click(screen.getByRole("option", { name: /Riya Patel/ }));

    expect(selected).toHaveBeenCalledWith("11");
    expect(screen.queryAllByRole("combobox")).toHaveLength(1);
  });
  it("keeps multiple remote choices in the open combobox", async () => {
    const user = userEvent.setup();
    const selected = vi.fn();
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AsyncSelect
            id="customers"
            label="Customers"
            value={[]}
            multiple
            onChange={selected}
            remote={leadOptions}
          />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("combobox", { name: "Customers" }));
    await user.click(await screen.findByRole("option", { name: /Riya Patel/ }));

    expect(selected).toHaveBeenCalledWith(["11"]);
  });
  it("keeps fallback labels paired with their missing multi-select values", async () => {
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AsyncSelect
            id="customers"
            label="Customers"
            value={["999", "11"]}
            multiple
            onChange={vi.fn()}
            remote={leadOptions}
          />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await screen.findByText(/Riya Patel/);
    expect(screen.getByLabelText("Selected customers")).toHaveTextContent(
      "Selected record (999)",
    );
  });
  it("does not submit an empty required remote choice", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    localStorage.setItem("estraos.session", JSON.stringify(session));
    localStorage.setItem("estraos.workspace", "1");
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RecordForm
            fields={[{ name: "leadId", label: "Customer", required: true, remote: leadOptions }]}
            onSubmit={submit}
          />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(screen.getByRole("combobox", { name: "Customer" })).toHaveAttribute(
      "aria-required",
      "true",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Customer is required.");
    expect(submit).not.toHaveBeenCalled();
  });
  it("selects a calendar day while retaining the chosen time", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <DateTimePicker
        id="scheduledAt"
        label="Date & time"
        value="2030-10-12T10:00"
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    expect(screen.getByText("October 2030")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "15 October 2030" }));

    expect(onChange).toHaveBeenCalledWith("2030-10-15T10:00");
  });
  it("preserves exact minutes and closes the calendar with Escape", async () => {
    const user = userEvent.setup();
    render(
      <DateTimePicker
        id="scheduledAt"
        label="Date & time"
        value="2030-10-12T10:07"
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    expect(screen.getByRole("textbox", { name: "Minutes" })).toHaveValue("07");
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Choose date & time" })).not.toBeInTheDocument();
  });
  it("uses inline time fields instead of nested dropdown menus", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <DateTimePicker
        id="visit-at"
        label="Date & time"
        value="2030-10-12T09:07"
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    expect(screen.getByRole("textbox", { name: "Hour" })).toHaveValue("09");
    expect(screen.getByRole("textbox", { name: "Minutes" })).toHaveValue("07");
    expect(screen.queryByRole("combobox", { name: "Hour" })).not.toBeInTheDocument();

    await user.clear(screen.getByRole("textbox", { name: "Minutes" }));
    await user.type(screen.getByRole("textbox", { name: "Minutes" }), "30");
    await user.tab();
    expect(onChange).toHaveBeenLastCalledWith("2030-10-12T09:30");
  });
  it("requests chronological site visit ordering before pagination", async () => {
    mount("/site-visits");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("sort=scheduledAt,asc"),
        expect.anything(),
      ),
    );
  });
  it("pages documents and refreshes persisted provider processing status", async () => {
    const user = userEvent.setup();
    const original = fetchMock.getMockImplementation() as (
      url: string,
      init?: RequestInit,
    ) => Promise<Response>;
    let state = "QUEUED";
    const doc = () => ({
      id: "71",
      title: "Older brochure",
      status: "PUBLISHED",
      processingStatus: state,
      content: "Readable content",
    });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes("/projects/21/documents"))
        return json({
          items: url.includes("page=1")
            ? [doc()]
            : [{ ...doc(), id: "70", title: "Recent brochure" }],
          total: 21,
          page: url.includes("page=1") ? 1 : 0,
          size: 10,
        });
      if (url.includes("/documents/71/processing-status")) {
        state = "READY";
        return json({ status: "READY", mock: true });
      }
      if (url.includes("/documents/71")) return json(doc());
      if (url.endsWith("/projects/21")) return json(project);
      return original(url, init);
    });
    mount("/projects/21/documents");
    await screen.findByText("Recent brochure");
    await user.click(screen.getByRole("button", { name: "Next page" }));
    await user.click(
      await screen.findByRole("button", { name: "Older brochure" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Refresh processing status" }),
    );
    await waitFor(() =>
      expect(screen.getAllByText("Ready").length).toBeGreaterThan(0),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/documents/71/processing-status"),
      expect.anything(),
    );
  });
  it("filters booking units by project and clears a prior unit on project change", async () => {
    const user = userEvent.setup();
    const fields = visitFields(
      [],
      [
        { id: "21", name: "Green" },
        { id: "22", name: "River" },
      ],
      [],
      [
        {
          id: "101",
          projectId: "21",
          unitNumber: "A-301",
          propertyType: "APARTMENT",
          status: "AVAILABLE",
        },
        {
          id: "102",
          projectId: "22",
          unitNumber: "B-301",
          propertyType: "APARTMENT",
          status: "AVAILABLE",
        },
      ],
    ).filter((f) => ["projectId", "unitId"].includes(f.name));
    render(<RecordForm fields={fields} onSubmit={vi.fn()} />);
    const unitSelect = screen.getByRole("combobox", { name: "Unit (optional)" });
    expect(unitSelect).toBeDisabled();
    await chooseOption(user, "Project", "Green");
    expect(
      screen.queryByRole("option", { name: /B-301/ }),
    ).not.toBeInTheDocument();
    await chooseOption(user, "Unit (optional)", /A-301/);
    expect(unitSelect).toHaveTextContent(/A-301/);
    await chooseOption(user, "Project", "River");
    expect(unitSelect).toHaveTextContent("Select unit (optional)");
    expect(
      screen.queryByRole("option", { name: /A-301/ }),
    ).not.toBeInTheDocument();
    await user.click(unitSelect);
    expect(screen.getByRole("option", { name: /B-301/ })).toBeInTheDocument();
  });
  it("preserves lakh and crore precision in compact prices", () => {
    expect(money(12000000)).toContain("1.2Cr");
    expect(money(7500000)).toContain("75L");
  });
  it("closes mobile navigation with Escape and restores toggle focus", async () => {
    const user = userEvent.setup();
    mount("/dashboard");
    const toggle = await screen.findByRole("button", {
      name: "Open navigation",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", "workspace-sidebar");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });
  it("rejects inverted budget ranges before submitting", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(
      <RecordForm
        fields={[
          { name: "budgetMin", label: "Minimum budget", type: "number" },
          { name: "budgetMax", label: "Maximum budget", type: "number" },
        ]}
        onSubmit={submit}
      />,
    );
    await user.type(screen.getByLabelText("Minimum budget"), "200");
    await user.type(screen.getByLabelText("Maximum budget"), "100");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByRole("alert")).toHaveTextContent("must not exceed");
    expect(submit).not.toHaveBeenCalled();
  });
  it("uses browser validation for required and email fields", () => {
    render(
      <RecordForm
        fields={[
          { name: "email", label: "Email", type: "email", required: true },
        ]}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Email *")).toBeRequired();
    expect(screen.getByLabelText("Email *")).toBeInvalid();
  });
  it("uses one bordered field for record search", () => {
    render(
      <Filters
        search=""
        onSearch={vi.fn()}
        status=""
        onStatus={vi.fn()}
        statuses={[]}
      />,
    );

    expect(screen.getByRole("textbox", { name: "Search records" })).toHaveClass(
      "search-box-input",
    );
  });
  it("prevents arrow keys from stepping number fields", () => {
    render(
      <RecordForm
        fields={[{ name: "duration", label: "Duration", type: "number" }]}
        initial={{ duration: 60 }}
        onSubmit={vi.fn()}
      />,
    );

    expect(
      fireEvent.keyDown(screen.getByLabelText("Duration"), { key: "ArrowUp" }),
    ).toBe(false);
  });
});
