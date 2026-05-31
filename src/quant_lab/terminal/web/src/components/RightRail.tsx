import { useState } from "react";

import type { DashboardSnapshot } from "../types/snapshot";
import { PanelShell } from "./PanelShell";
import { PinPanel } from "./PinPanel";
import { PlaybookPanel } from "./PlaybookPanel";
import { RegimePanel } from "./RegimePanel";

type RailTab = "playbook" | "pin" | "regime";

/** Right column: Playbook (sizing) · Pin (magnets) · Regime (context). */
export function RightRail({ snapshot }: { snapshot: DashboardSnapshot }) {
  const [tab, setTab] = useState<RailTab>("playbook");

  return (
    <PanelShell className="right-rail" spotlightColor="rgba(20, 184, 166, 0.04)">
      <div className="rail-tabs" role="tablist" aria-label="Side panel">
        <button
          type="button"
          role="tab"
          className={`rail-tab${tab === "playbook" ? " active" : ""}`}
          aria-selected={tab === "playbook"}
          onClick={() => setTab("playbook")}
        >
          Playbook
        </button>
        <button
          type="button"
          role="tab"
          className={`rail-tab${tab === "pin" ? " active" : ""}`}
          aria-selected={tab === "pin"}
          onClick={() => setTab("pin")}
        >
          Pin
        </button>
        <button
          type="button"
          role="tab"
          className={`rail-tab${tab === "regime" ? " active" : ""}`}
          aria-selected={tab === "regime"}
          onClick={() => setTab("regime")}
        >
          Regime
        </button>
      </div>
      <div className="rail-panel-host">
        {tab === "playbook" ? <PlaybookPanel snapshot={snapshot} /> : null}
        {tab === "pin" ? <PinPanel snapshot={snapshot} /> : null}
        {tab === "regime" ? <RegimePanel snapshot={snapshot} /> : null}
      </div>
    </PanelShell>
  );
}
