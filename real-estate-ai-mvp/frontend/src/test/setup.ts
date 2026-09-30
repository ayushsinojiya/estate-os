import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
  value: function () {
    this.setAttribute("open", "");
  },
  configurable: true,
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
  value: function () {
    this.removeAttribute("open");
  },
  configurable: true,
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});
