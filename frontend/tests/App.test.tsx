import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "../src/App";


test("renders the AgentDesk frontend title", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "AgentDesk" })).toBeInTheDocument();
});
