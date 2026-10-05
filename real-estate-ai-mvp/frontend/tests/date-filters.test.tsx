import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataTable, Filters } from "../src/components/ui";
import { DateTimePicker } from "../src/components/DateTimePicker";
import { useList } from "../src/hooks/useList";
import { useApi } from "../src/hooks/useApi";

vi.mock("../src/hooks/useApi", () => ({ useApi: vi.fn(() => ({ data: { items: [], total: 0, page: 0, size: 10 } })) }));

describe("table date filters", () => {
  it("filters embedded rows by both inclusive local dates and can clear the range", () => {
    render(<DataTable data={[
      { id: "1", createdAt: "2026-10-01T10:00:00Z", name: "Earlier" },
      { id: "2", createdAt: "2026-10-05T10:00:00Z", name: "In range" },
      { id: "3", createdAt: "2026-10-06T10:00:00Z", name: "Later" },
    ]} columns={[{ key: "name", label: "Name" }, { key: "createdAt", label: "Created" }]} />);

    fireEvent.click(screen.getByRole("button", { name: "Select from date" }));
    fireEvent.click(screen.getByRole("button", { name: "5 October 2026" }));
    fireEvent.click(screen.getByRole("button", { name: "Select to date" }));
    fireEvent.click(screen.getByRole("button", { name: "5 October 2026" }));

    expect(screen.queryByText("Earlier")).not.toBeInTheDocument();
    expect(screen.getByText("In range")).toBeInTheDocument();
    expect(screen.queryByText("Later")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear dates" }));
    expect(screen.getByText("Earlier")).toBeInTheDocument();
    expect(screen.getByText("Later")).toBeInTheDocument();
  });

  it("does not offer a date filter for a table without dates", () => {
    render(<DataTable data={[{ id: "1", name: "No date" }]} columns={[{ key: "name", label: "Name" }]} />);
    expect(screen.queryByRole("button", { name: "Select from date" })).not.toBeInTheDocument();
  });

  it("offers controlled date filters on paginated lists", () => {
    const onDateFrom = vi.fn();
    render(<Filters search="" onSearch={vi.fn()} status="" onStatus={vi.fn()} statuses={[]}
      dateFrom="" dateTo="" onDateFrom={onDateFrom} onDateTo={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Select from date" }));
    fireEvent.click(screen.getByRole("button", { name: "5 October 2026" }));
    expect(onDateFrom).toHaveBeenCalledWith("2026-10-05");
  });

  it("date-only mode has no time inputs", () => {
    render(<DateTimePicker id="date" label="From date" value="2026-10-05" onChange={vi.fn()} dateOnly />);
    fireEvent.click(screen.getByRole("button", { name: "Select from date" }));
    expect(screen.queryByRole("textbox", { name: "Hour" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Minutes" })).not.toBeInTheDocument();
  });

  it("marks the current day and lets users jump to today", () => {
    const today = new Date();
    const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    const onChange = vi.fn();
    render(<DateTimePicker id="today" label="From date" value="" onChange={onChange} dateOnly />);
    fireEvent.click(screen.getByRole("button", { name: "Select from date" }));
    expect(screen.getByRole("button", { name: new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" }).format(today) })).toHaveAttribute("aria-current", "date");
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(onChange).toHaveBeenCalledWith(day);
  });

  it("resets pagination and sends local date bounds as UTC instants", () => {
    const { result } = renderHook(() => useList("/leads"));
    act(() => result.current.setPage(3));
    act(() => result.current.onDateFrom("2026-10-05"));
    act(() => result.current.onDateTo("2026-10-05"));
    expect(result.current.page).toBe(0);
    expect(vi.mocked(useApi).mock.lastCall?.[0]).toContain(`dateFrom=${encodeURIComponent(new Date(2026, 9, 5).toISOString())}`);
    expect(vi.mocked(useApi).mock.lastCall?.[0]).toContain(`dateTo=${encodeURIComponent(new Date(2026, 9, 6).toISOString())}`);
  });

  it("can jump directly to a month and year in the custom calendar", () => {
    render(<DateTimePicker id="jump" label="From date" value="2026-10-05" onChange={vi.fn()} dateOnly />);
    fireEvent.click(screen.getByRole("button", { name: "Select from date" }));
    fireEvent.click(screen.getByRole("button", { name: "Choose month" }));
    fireEvent.click(screen.getByRole("button", { name: "March" }));
    expect(screen.getByRole("button", { name: "Choose month" })).toHaveTextContent("March");
    fireEvent.click(screen.getByRole("button", { name: "Choose year" }));
    fireEvent.click(screen.getByRole("button", { name: "2030" }));
    expect(screen.getByRole("button", { name: "Choose year" })).toHaveTextContent("2030");
  });
});
