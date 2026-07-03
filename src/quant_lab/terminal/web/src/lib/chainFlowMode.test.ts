import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadChainFlowMode, saveChainFlowMode } from "./chainFlowMode";

function mockLocalStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    clear: () => {
      store.clear();
    },
  };
}

function stubWindow(hostname: string) {
  const storage = mockLocalStorage();
  vi.stubGlobal("window", {
    location: { hostname },
    localStorage: storage,
  });
  vi.stubGlobal("localStorage", storage);
}

describe("loadChainFlowMode", () => {
  beforeEach(() => {
    stubWindow("localhost");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns stored preference when set", () => {
    saveChainFlowMode("pin");
    expect(loadChainFlowMode()).toBe("pin");
    saveChainFlowMode("full");
    expect(loadChainFlowMode()).toBe("full");
  });

  it("defaults to Precise on non-local hosts without stored preference", () => {
    stubWindow("quantlab-terminal-production.up.railway.app");
    expect(loadChainFlowMode()).toBe("full");
  });

  it("defaults to Fast on localhost without stored preference", () => {
    expect(loadChainFlowMode()).toBe("pin");
  });
});
