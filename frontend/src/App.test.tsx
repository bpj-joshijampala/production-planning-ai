import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the app shell and connected backend state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        }),
      }),
    );

    render(<App />);

    expect(screen.getByRole("heading", { name: "Production Planning AI" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Machine Load" })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });
  });

  it("shows a friendly unavailable state when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Backend unavailable")).toBeInTheDocument();
    });
  });
});
