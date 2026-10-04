import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { configureApi } from "../src/api/client";
import { CallOutcome, DncBanner, MarkDnc, VisitBadges } from "../src/features/voice";

const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  configureApi("crm-token", "7");
  fetchMock = vi.fn(async () => json({ dnc: true, created: true }));
  vi.stubGlobal("fetch", fetchMock);
});

describe("voice agent additions", () => {
  it("shows a do-not-call banner only for a listed number", () => {
    const { rerender } = render(<DncBanner lead={{ id: "1", dnc: false }} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(<DncBanner lead={{ id: "1", dnc: true, doNotCallBasis: "explicit" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Do not call");
    expect(screen.getByRole("alert")).toHaveTextContent("explicit");
  });

  it("adds a lead's number to the do-not-call list", async () => {
    const user = userEvent.setup();
    render(<MarkDnc lead={{ id: "42", phone: "+919800000001" }} />);
    await user.click(screen.getByRole("button", { name: "Do not call" }));
    await user.type(screen.getByLabelText("Reason"), "Asked on the phone");
    await user.click(screen.getByRole("button", { name: /Add to do-not-call list/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/dnc", expect.objectContaining({ method: "POST" })));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ phone: "+919800000001", reason: "Asked on the phone", leadId: "42" });
  });

  it("marks visits Riya booked and visits that need review", () => {
    render(<VisitBadges visit={{ id: "1", bookedBy: "VOICE_AGENT", needsManagerReview: true }} />);
    expect(screen.getByText("Booked By Riya")).toBeInTheDocument();
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
  });

  it("shows what the call recorded beyond the transcript", () => {
    render(<CallOutcome call={{ id: "9", callType: "INBOUND", leadTemperature: "HOT", leadScore: 85,
      unansweredQuestions: ["Is there a festive discount?"], citations: ["301"] }} />);
    expect(screen.getByText("HOT")).toBeInTheDocument();
    expect(screen.getByText("Is there a festive discount?")).toBeInTheDocument();
    expect(screen.getByText(/#301/)).toBeInTheDocument();
  });
});
