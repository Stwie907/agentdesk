import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

beforeEach(() => { window.localStorage.clear(); });

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
  try { window.localStorage.clear(); } catch { /* Storage failures are deliberately tested. */ }
});
