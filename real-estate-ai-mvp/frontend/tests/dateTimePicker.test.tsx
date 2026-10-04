import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DateTimePicker } from "../src/components/DateTimePicker";

function rect(left: number, top: number, width: number, height: number) {
  return new DOMRect(left, top, width, height);
}

function mockRects(dialog: DOMRect, trigger: DOMRect, menu: DOMRect) {
  const original = HTMLElement.prototype.getBoundingClientRect;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this instanceof HTMLDialogElement) return dialog;
    if (this.classList.contains("date-time-picker-trigger")) return trigger;
    if (this.classList.contains("date-time-picker-menu")) return menu;
    return original.call(this);
  });
}

afterEach(() => vi.restoreAllMocks());

describe("date picker popup placement", () => {
  it("escapes a short modal's scroll area without leaving the viewport", async () => {
    vi.stubGlobal("innerWidth", 1280);
    vi.stubGlobal("innerHeight", 720);
    mockRects(rect(300, 200, 680, 320), rect(321, 309, 305, 41), rect(0, 0, 440, 254));
    const user = userEvent.setup();
    render(<dialog open><DateTimePicker id="dueAt" label="Call back at" value="" onChange={vi.fn()} /></dialog>);

    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    const menu = screen.getByRole("dialog", { name: "Choose call back at" });
    expect(menu).toHaveStyle({ position: "fixed" });
    expect(Number.parseFloat(menu.style.top)).toBeGreaterThanOrEqual(16);
    expect(Number.parseFloat(menu.style.top) + 254).toBeLessThanOrEqual(704);
  });

  it("keeps the popup within a narrow modal and makes tall content scrollable", async () => {
    vi.stubGlobal("innerWidth", 390);
    vi.stubGlobal("innerHeight", 600);
    mockRects(rect(16, 30, 358, 540), rect(40, 250, 200, 41), rect(0, 0, 440, 650));
    const user = userEvent.setup();
    render(<dialog open><DateTimePicker id="dueAt" label="Call back at" value="" onChange={vi.fn()} /></dialog>);

    await user.click(screen.getByRole("button", { name: "Select date and time" }));
    const menu = screen.getByRole("dialog", { name: "Choose call back at" });
    expect(Number.parseFloat(menu.style.width)).toBeLessThanOrEqual(326);
    expect(Number.parseFloat(menu.style.left)).toBeGreaterThanOrEqual(32);
    expect(Number.parseFloat(menu.style.left) + Number.parseFloat(menu.style.width)).toBeLessThanOrEqual(358);
    expect(Number.parseFloat(menu.style.maxHeight)).toBeLessThanOrEqual(568);
  });
});
