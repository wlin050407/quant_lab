import { useState } from "react";



import type { EquityAnalyzeResponse, HorizonBias, ModuleId } from "../../types/equity";

import { useLocale } from "../../hooks/useLocale";

import { getEquityStrings, translateBackendReason } from "../../lib/i18n/equityStrings";

import {

  distFromSpot,

  formatAdv,

  formatRs,

  horizonEntries,

  maVsSpot,

} from "../../lib/equityDisplay";

import { resolveModuleSignals } from "../../lib/equityModuleSignals";

import { fmtPct, fmtPrice } from "../../lib/format";



import { PanelShell } from "../PanelShell";

import { EquityBiasChip } from "./EquityModuleParts";

import { EquityHorizonPanel } from "./EquityHorizonPanel";

import { EquityRsBars } from "./EquityRsBars";



type RailTab = "signals" | "horizons";



const MODULE_ROWS: ModuleId[] = [

  "vwap_flow",

  "volume_profile",

  "trend",

  "options_flow",

  "liquidity",

  "context",

];



const LAYER: Record<ModuleId, keyof EquityAnalyzeResponse["layers"]> = {

  vwap_flow: "L2",

  volume_profile: "L3",

  trend: "L5",

  options_flow: "L6",

  liquidity: "L0",

  context: "L1",

};



type DetailRow = { label: string; value: string };



function moduleExplain(data: EquityAnalyzeResponse, id: ModuleId, locale: "en" | "zh"): string {

  const raw = getEquityStrings(locale).modules[id].explain;

  return raw.replaceAll("{bench}", data.benchmark);

}



function metricForModule(data: EquityAnalyzeResponse, id: ModuleId, locale: "en" | "zh"): string {

  const l0 = data.layers.L0;

  const l1 = data.layers.L1;

  const l2 = data.layers.L2;

  const l3 = data.layers.L3;

  const l5 = data.layers.L5;

  const l6 = data.layers.L6;

  const spot = data.spot;

  const s = getEquityStrings(locale);



  switch (id) {

    case "vwap_flow":

      if (Number.isFinite(l2.rs_open_30m ?? NaN)) {
        return `${l2.above_vwap ? "+" : "-"}${fmtPct(Math.abs(l2.deviation_pct))} VWAP · O30 ${formatRs(l2.rs_open_30m!)}`;
      }
      return `${l2.above_vwap ? "+" : "-"}${fmtPct(Math.abs(l2.deviation_pct))} VWAP`;

    case "volume_profile":

      return `POC ${fmtPrice(l3.poc)} ${distFromSpot(spot, l3.poc) ?? ""}`.trim();

    case "trend":

      return `RS20 ${formatRs(l5.rs_20d)} · MA200 ${maVsSpot(spot, l5.ma200) === "above" ? "↑" : "↓"}`;

    case "options_flow":

      return l6 ? `PCR ${l6.pcr_volume.toFixed(2)} · MP ${fmtPrice(l6.max_pain)}` : "—";

    case "liquidity":

      return `${formatAdv(l0.adv_usd)} · ${l0.eligible ? "OK" : "LOW"}`;

    case "context":

      return l1.earnings_window ? (locale === "zh" ? "财报 ≤7d" : "Earnings ≤7d") : s.clear;

    default:

      return "—";

  }

}



function detailRowsForModule(data: EquityAnalyzeResponse, id: ModuleId, locale: "en" | "zh"): DetailRow[] {

  const s = getEquityStrings(locale);

  const f = s.fields;

  const spot = data.spot;

  const l0 = data.layers.L0;

  const l1 = data.layers.L1;

  const l2 = data.layers.L2;

  const l3 = data.layers.L3;

  const l5 = data.layers.L5;

  const l6 = data.layers.L6;



  switch (id) {

    case "liquidity":

      return [

        { label: f.adv, value: formatAdv(l0.adv_usd) },

        { label: f.amihud, value: l0.amihud.toExponential(2) },

        { label: f.eligible, value: l0.eligible ? s.yes : s.lowLiquidity },

        { label: s.grade, value: l0.grade },

      ];

    case "context":

      return [

        { label: f.volRegime, value: s.volRegimeMap[l1.vol_regime as keyof typeof s.volRegimeMap] ?? l1.vol_regime },

        { label: f.earnings, value: l1.earnings_window ? s.yes : s.clear },

        {

          label: f.macro,

          value: l1.macro_events.length > 0 ? l1.macro_events.map((e) => e.label).join(", ") : s.noneMacro,

        },

        { label: s.grade, value: l1.grade },

      ];

    case "vwap_flow":

      return [

        { label: f.vwap, value: fmtPrice(l2.vwap) },

        { label: f.last, value: fmtPrice(l2.last) },

        { label: f.deviation, value: `${l2.above_vwap ? "+" : "-"}${fmtPct(Math.abs(l2.deviation_pct))}` },

        ...(Number.isFinite(l2.rs_open_30m ?? NaN)
          ? [{ label: f.rsOpen30m, value: formatRs(l2.rs_open_30m!) }]
          : []),

        { label: s.vsVwap, value: l2.above_vwap ? s.above : s.below },

        { label: s.grade, value: l2.grade },

      ];

    case "volume_profile":

      return [

        { label: f.poc, value: `${fmtPrice(l3.poc)} ${distFromSpot(spot, l3.poc) ?? ""}`.trim() },

        { label: f.vah, value: fmtPrice(l3.vah) },

        { label: f.val, value: fmtPrice(l3.val) },

        { label: s.grade, value: l3.grade },

      ];

    case "trend":

      return [

        { label: f.rs1d, value: formatRs(l5.rs_1d) },

        { label: f.rs20d, value: formatRs(l5.rs_20d) },

        { label: f.ma20, value: `${fmtPrice(l5.ma20)} (${maVsSpot(spot, l5.ma20) === "above" ? s.spotAbove : s.spotBelow})` },

        { label: f.ma200, value: `${fmtPrice(l5.ma200)} (${maVsSpot(spot, l5.ma200) === "above" ? s.spotAbove : s.spotBelow})` },

        { label: s.grade, value: l5.grade },

      ];

    case "options_flow":

      if (!l6) {

        return [{ label: s.status, value: s.chainUnavailable }];

      }

      return [

        { label: f.pcrVol, value: l6.pcr_volume.toFixed(2) },

        { label: f.pcrOi, value: l6.pcr_oi.toFixed(2) },

        { label: f.maxPain, value: `${fmtPrice(l6.max_pain)} ${distFromSpot(spot, l6.max_pain) ?? ""}`.trim() },

        { label: f.contracts, value: String(l6.n_contracts) },

        { label: s.grade, value: l6.grade },

      ];

    default:

      return [];

  }

}



function biasRowClass(bias: HorizonBias): string {

  if (bias === "bullish") return "eq-row--bull";

  if (bias === "bearish") return "eq-row--bear";

  return "";

}



function toggleModule(expanded: ModuleId | null, id: ModuleId): ModuleId | null {

  return expanded === id ? null : id;

}



export function EquityResearchRail({ data }: { data: EquityAnalyzeResponse }) {

  const { locale } = useLocale();

  const s = getEquityStrings(locale);

  const [tab, setTab] = useState<RailTab>("signals");

  const [hz, setHz] = useState<"short" | "mid" | "long">("short");

  const [expanded, setExpanded] = useState<ModuleId | null>(null);

  const modules = resolveModuleSignals(data);

  const weakest = data.horizons.weakest_link;



  return (

    <PanelShell className="right-rail equity-rail" spotlightColor="rgba(20, 184, 166, 0.04)">

      <div className="rail-tabs" role="tablist">

        <button

          type="button"

          role="tab"

          className={`rail-tab${tab === "signals" ? " active" : ""}`}

          aria-selected={tab === "signals"}

          onClick={() => setTab("signals")}

        >

          {s.tabs.signals}

        </button>

        <button

          type="button"

          role="tab"

          className={`rail-tab${tab === "horizons" ? " active" : ""}`}

          aria-selected={tab === "horizons"}

          onClick={() => setTab("horizons")}

        >

          {s.tabs.horizons}

        </button>

      </div>



      <div className="rail-panel-host">

        {tab === "signals" ? (

          <div className="eq-monitor">

            <p className="eq-monitor__lead">

              {s.moduleDeckLead} {s.expandHint}

            </p>

            <div className="eq-signal-list" role="list">

              {MODULE_ROWS.map((id) => {

                const layerKey = LAYER[id];

                const layerMeta = s.layers[layerKey as "L0" | "L1" | "L2" | "L3" | "L5" | "L6"];

                const mod = modules[id];

                const isOpen = expanded === id;

                const details = detailRowsForModule(data, id, locale);



                return (

                  <article

                    key={id}

                    className={`eq-signal-row ${biasRowClass(mod.bias)}${isOpen ? " is-open" : ""}`}

                    role="listitem"

                  >

                    <button

                      type="button"

                      className="eq-signal-row__head"

                      aria-expanded={isOpen}

                      onClick={() => setExpanded((prev) => toggleModule(prev, id))}

                    >

                      <span className="eq-signal-row__main">

                        <span className="eq-monitor-table__layer">{layerKey}</span>

                        <span className="eq-monitor-table__name">{s.modules[id].title}</span>

                        <span className="eq-monitor-table__sub">{s.modules[id].sub.replace("{bench}", data.benchmark)}</span>

                      </span>

                      <span className="eq-signal-row__aside">

                        <EquityBiasChip bias={mod.bias} compact />

                        <span className="eq-monitor-table__metric">{metricForModule(data, id, locale)}</span>

                        <span className="eq-signal-row__chevron" aria-hidden>

                          {isOpen ? "▾" : "▸"}

                        </span>

                      </span>

                    </button>



                    {isOpen ? (

                      <div className="eq-signal-row__detail">

                        <p className="eq-signal-row__explain">{moduleExplain(data, id, locale)}</p>

                        <p className="eq-signal-row__layer-title">

                          {layerMeta.title} · {layerMeta.sub.replace("{bench}", data.benchmark)}

                        </p>

                        <dl className="eq-signal-row__facts">

                          {details.map(({ label, value }) => (

                            <div key={label} className="eq-signal-row__fact">

                              <dt>{label}</dt>

                              <dd>{value}</dd>

                            </div>

                          ))}

                          <div className="eq-signal-row__fact">

                            <dt>{s.moduleScore}</dt>

                            <dd>{Math.round(mod.score * 100)}</dd>

                          </div>

                        </dl>

                        {id === "trend" ? (

                          <div className="eq-signal-row__rs">

                            <EquityRsBars

                              rs1d={data.layers.L5.rs_1d}

                              rs5d={data.layers.L5.rs_5d}

                              rs20d={data.layers.L5.rs_20d}

                              rs60d={data.layers.L5.rs_60d}

                              rs120d={data.layers.L5.rs_120d}

                            />

                          </div>

                        ) : null}

                      </div>

                    ) : null}

                  </article>

                );

              })}

            </div>

            {weakest ? (

              <p className="eq-monitor-warn">

                <strong>

                  {s.weakest} · {weakest.layer}

                </strong>

                {translateBackendReason(locale, weakest.reason)}

              </p>

            ) : null}

          </div>

        ) : (

          <div className="eq-horizon-rail">

            <table className="eq-monitor-table eq-monitor-table--horizons">

              <thead>

                <tr>

                  <th>{s.tableHorizon}</th>

                  <th>{s.tableBias}</th>

                  <th>{s.tableConf}</th>

                </tr>

              </thead>

              <tbody>

                {horizonEntries(data.horizons).map(({ key, verdict }) => {

                  const meta = s.horizons[key];

                  return (

                    <tr

                      key={key}

                      className={`${biasRowClass(verdict.bias)}${hz === key ? " is-selected" : ""}`}

                      onClick={() => setHz(key)}

                      role="button"

                      tabIndex={0}

                      onKeyDown={(e) => e.key === "Enter" && setHz(key)}

                    >

                      <td>

                        <span className="eq-monitor-table__name">{meta.title}</span>

                        <span className="eq-monitor-table__sub">{meta.window}</span>

                      </td>

                      <td>

                        <EquityBiasChip bias={verdict.bias} compact />

                      </td>

                      <td className="eq-monitor-table__metric">{Math.round(verdict.confidence * 100)}%</td>

                    </tr>

                  );

                })}

              </tbody>

            </table>

            <EquityHorizonPanel horizonKey={hz} verdict={data.horizons[hz]} />

          </div>

        )}

      </div>

    </PanelShell>

  );

}


