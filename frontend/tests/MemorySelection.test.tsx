import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { HomePage } from "../src/pages/HomePage";
import { jsonResponse, testAgent } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

test("the task selector controls the memory panel and resets drafts when scope changes", async () => {
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), "http://localhost").pathname;
    requests.push(path);
    if (path === "/agents") return jsonResponse([testAgent, { ...testAgent, id: 8, name: "Other Agent" }]);
    if (path === "/executions" || path === "/conversations" || path.startsWith("/memories/")) return jsonResponse([]);
    throw new Error(`Unexpected request: ${path}`);
  }));
  render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  const panel = within(screen.getByRole("heading", { name: "Agent Memory" }).closest("section")!);
  expect(panel.getByText(/Select an Agent above/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "7" } });
  await panel.findByText("No saved memories for this Agent.");
  fireEvent.change(panel.getByLabelText("Memory content"), { target: { value: "Old draft" } });
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "8" } });
  await panel.findByText("Memories for Agent 8");
  await panel.findByText("No saved memories for this Agent.");
  expect(panel.getByLabelText("Memory content")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "" } });
  expect(await panel.findByText(/Select an Agent above/)).toBeInTheDocument();
  expect(requests.filter((path) => path.startsWith("/memories"))).toEqual(["/memories/7", "/memories/8"]);
  expect(requests.filter((path) => path === "/agents")).toHaveLength(1);
});
