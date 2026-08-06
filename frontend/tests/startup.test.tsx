import { screen } from "@testing-library/react";
import { expect, test } from "vitest";


test("mounts the application in the root element", async () => {
  document.body.innerHTML = '<div id="root"></div>';

  await import("../src/main");

  expect(await screen.findByRole("heading", { name: "AgentDesk" })).toBeInTheDocument();
});
