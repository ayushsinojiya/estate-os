import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Details, PageHeader } from "../components/ui";
import { AuthProvider } from "../hooks/useAuth";
import { App } from "../routes/App";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  document.title = "EstraOS";
  document.querySelector('meta[name="description"]')?.remove();
  const meta = document.createElement("meta");
  meta.name = "description";
  meta.content = "Default description";
  document.head.append(meta);
});

describe("website quality", () => {
  it("uses the current page heading for browser metadata", async () => {
    render(<PageHeader title="Your leads" description="Manage customer leads." />);

    await waitFor(() => {
      expect(document.title).toBe("Your leads | EstraOS");
      expect(document.querySelector('meta[name="description"]')).toHaveAttribute(
        "content",
        "Manage customer leads.",
      );
    });
  });

  it("shows a useful 404 for an unknown route", async () => {
    render(
      <MemoryRouter initialEntries={["/not-a-page"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
  });

  it("links real phone and email contact fields", () => {
    render(<Details data={{ phone: "+91 98765 43210", email: "riya@example.com" }} fields={["phone", "email"]} />);

    expect(screen.getByRole("link", { name: "+91 98765 43210" })).toHaveAttribute("href", "tel:+919876543210");
    expect(screen.getByRole("link", { name: "riya@example.com" })).toHaveAttribute("href", "mailto:riya@example.com");
  });

  it("does not link missing contact fields", () => {
    render(<Details data={{ phone: "", email: null }} fields={["phone", "email"]} />);

    expect(screen.getAllByText("Not provided")).toHaveLength(2);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("leaves malformed contact values as plain text", () => {
    render(<Details data={{ phone: "Call me soon", email: "not-an-address" }} fields={["phone", "email"]} />);

    expect(screen.getByText("Call me soon")).toBeInTheDocument();
    expect(screen.getByText("not-an-address")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
