import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CallDetail } from "../src/pages/Calls";
import { write } from "../src/api/client";

const transcript = Array.from({ length: 6 }, (_, index) => ({
  speaker: index % 2 ? "caller" : "agent",
  text: `Message ${index + 1}`,
}));
let callStatus = "COMPLETED";

vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({
    isPending: false,
    error: null,
    refetch: vi.fn(),
    data: { status: callStatus, leadId: "12", transcript },
  }),
}));
vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => ({ canManage: true }) }));
vi.mock("../src/api/client", () => ({ write: vi.fn().mockResolvedValue(undefined) }));
vi.mock("../src/services/query", () => ({ queryClient: { invalidateQueries: vi.fn() } }));

describe("conversation transcript", () => {
  it("keeps a long transcript in its own keyboard-accessible region", () => {
    render(
      <MemoryRouter initialEntries={["/calls/34"]}>
        <Routes>
          <Route path="/calls/:id" element={<CallDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    const region = screen.getByRole("region", { name: "Transcript" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getAllByText(/Message \d/)).toHaveLength(6);
  });
});

it("confirms removal of a completed conversation", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/calls/34"]}>
      <Routes>
        <Route path="/calls/:id" element={<CallDetail />} />
        <Route path="/calls" element={<div>Conversations list</div>} />
      </Routes>
    </MemoryRouter>,
  );
  await user.click(screen.getByRole("button", { name: "Remove conversation" }));
  expect(write).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  expect(write).toHaveBeenCalledWith("/calls/34", null, "DELETE");
  expect(await screen.findByText("Conversations list")).toBeInTheDocument();
});

it("does not offer removal while a conversation is in progress", () => {
  callStatus = "IN_PROGRESS";
  try {
    render(
      <MemoryRouter initialEntries={["/calls/34"]}>
        <Routes><Route path="/calls/:id" element={<CallDetail />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: "Remove conversation" })).not.toBeInTheDocument();
  } finally {
    callStatus = "COMPLETED";
  }
});
