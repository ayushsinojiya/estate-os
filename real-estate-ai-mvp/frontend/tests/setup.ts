// Node 25+ defines its own localStorage/sessionStorage globals, which are undefined unless Node
// runs with --localstorage-file, and which shadow jsdom's. Put jsdom's back so the suite behaves
// the same on every supported Node version.
for (const name of ["localStorage", "sessionStorage"] as const) {
  if (!globalThis[name]) {
    const jsdomWindow = (globalThis as unknown as { jsdom?: { window: Window } }).jsdom?.window;
    if (jsdomWindow)
      Object.defineProperty(globalThis, name, { value: jsdomWindow[name], configurable: true, writable: true });
  }
}
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
