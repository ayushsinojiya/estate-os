import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "../services/query";
import { AuthProvider } from "../hooks/useAuth";
import { ToastProvider, RecordForm } from "../components/ui";
import { App } from "../routes/App";
import { money } from "../utils/format";
import { visitFields, leadOptions, unitFields } from "../features/fields";
const session = {
  token: "test-token",
  user: { id: "1", name: "Anaya Shah", email: "admin@estateos.demo" },
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
    sessionStorage.setItem("estateos.session", JSON.stringify(session));
    sessionStorage.setItem("estateos.workspace", "1");
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
  it("protects workspace routes from unauthenticated visitors", async () => {
    mount("/projects", false);
    expect(
      await screen.findByRole("heading", { name: "Let’s get you settled in." }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("signs in and sends the returned workspace context on API calls", async () => {
    const user = userEvent.setup();
    mount("/login", false);
    await user.type(screen.getByLabelText("Work email"), "admin@estateos.demo");
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
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: /The Green Residences/ }),
      ).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByLabelText(/^Project/), "21");
    await user.selectOptions(screen.getByLabelText(/^Assigned agent/), "3");
    await user.type(screen.getByLabelText(/^Date & time/), "2030-10-12T10:00");
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
    await user.selectOptions(screen.getByLabelText("Building / tower *"), "1");
    await user.selectOptions(screen.getByLabelText("Catalog floor"), "10");
    expect(
      screen.queryByRole("option", { name: "Floor 4" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Building / tower *"), "2");
    expect(screen.getByLabelText("Catalog floor")).toHaveValue("");
    expect(screen.getByRole("option", { name: "Floor 4" })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Corner apartment" }),
    ).toBeInTheDocument();
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
    sessionStorage.setItem("estateos.session", JSON.stringify(session));
    sessionStorage.setItem("estateos.workspace", "1");
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
    expect(
      await screen.findByRole("option", { name: /Saved distant lead/ }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Next customer options" }),
    );
    expect(
      await screen.findByRole("option", { name: /Beyond first hundred/ }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Customer")).toHaveValue("999");
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
    const projectSelect = screen.getByLabelText("Project *");
    const unitSelect = screen.getByLabelText("Unit (optional)");
    expect(unitSelect).toBeDisabled();
    await user.selectOptions(projectSelect, "21");
    expect(
      screen.queryByRole("option", { name: /B-301/ }),
    ).not.toBeInTheDocument();
    await user.selectOptions(unitSelect, "101");
    expect(unitSelect).toHaveValue("101");
    await user.selectOptions(projectSelect, "22");
    expect(unitSelect).toHaveValue("");
    expect(
      screen.queryByRole("option", { name: /A-301/ }),
    ).not.toBeInTheDocument();
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
});
