import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CallDetail } from "../src/pages/Calls";

const transcript = Array.from({ length: 6 }, (_, index) => ({
  speaker: index % 2 ? "caller" : "agent",
  text: `Message ${index + 1}`,
}));

vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({
    isPending: false,
    error: null,
    refetch: vi.fn(),
    data: { status: "COMPLETED", leadId: "12", transcript },
  }),
}));

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
