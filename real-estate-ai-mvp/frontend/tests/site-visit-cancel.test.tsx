import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { SiteVisitDetail, SiteVisits } from "../src/pages/SiteVisits";
import { write } from "../src/api/client";

const visit = {
  id: "42", leadId: "12", projectId: "9", agentId: "3",
  scheduledAt: "2026-10-07T10:00:00Z", durationMinutes: 60,
  status: "CONFIRMED", notes: "Meet in lobby",
};
let visitStatus = "CONFIRMED";

vi.mock("../src/hooks/useApi", () => ({
  useApi: (path: string) => ({
    isPending: false, error: null, refetch: vi.fn(),
    data: path === "/site-visits/42" ? { ...visit, status: visitStatus } : [],
  }),
}));
vi.mock("../src/hooks/useList", () => ({
  useList: () => ({
    query: { isPending: false, error: null, refetch: vi.fn(),
      data: { items: [{ ...visit, status: visitStatus }], total: 1, page: 0, size: 10 } },
    search: "", status: "", sort: "scheduledAt,asc", page: 0,
    setPage: vi.fn(), onSearch: vi.fn(), onStatus: vi.fn(), onSort: vi.fn(),
  }),
}));
vi.mock("../src/api/client", () => ({ write: vi.fn().mockResolvedValue(undefined) }));
vi.mock("../src/services/query", () => ({ queryClient: { invalidateQueries: vi.fn() } }));

it("confirms cancellation and retains the visit record", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/site-visits/42"]}>
      <Routes><Route path="/site-visits/:id" element={<SiteVisitDetail />} /></Routes>
    </MemoryRouter>,
  );
  await user.click(screen.getAllByRole("button", { name: "Cancel visit" })[0]);
  expect(write).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Confirm status change" }));
  expect(write).toHaveBeenCalledWith(
    "/site-visits/42", expect.objectContaining({ status: "CANCELLED", leadId: "12" }), "PUT",
  );
});

it("does not offer cancellation for a completed visit", () => {
  visitStatus = "COMPLETED";
  try {
    render(
      <MemoryRouter initialEntries={["/site-visits/42"]}>
        <Routes><Route path="/site-visits/:id" element={<SiteVisitDetail />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: "Cancel visit" })).toBeDisabled();
  } finally {
    visitStatus = "CONFIRMED";
  }
});

it("offers cancellation directly in the default schedule view", async () => {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/site-visits"]}><SiteVisits /></MemoryRouter>);
  expect(document.querySelector(".visit-slot-main")).toHaveAttribute("href", "/site-visits/42");
  await user.click(screen.getByRole("button", { name: "Cancel visit" }));
  expect(screen.getByRole("heading", { name: "Cancel site visit?" })).toBeVisible();
});
