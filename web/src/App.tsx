import { useEffect, useState } from "react";
import { Panel } from "./components/Panel";
import { ExposurePanel } from "./components/ExposurePanel";
import { apiGet } from "./api/client";
import type { Freshness } from "./api/types";

// v1 modules (M1 cut per user decision 2026-10-01, option D).
const MODULES = [
  { key: "m3", title: "板块动量 / 轮动", phase: "Phase 2" },
  { key: "m4", title: "聪明钱（13F / 内幕）", phase: "Phase 3" },
  { key: "m5", title: "期权情绪", phase: "Phase 4" },
] as const;

export function App() {
  const [fresh, setFresh] = useState<Record<string, Freshness | null>>({});

  useEffect(() => {
    apiGet<Freshness[]>("/freshness")
      .then((rows) =>
        setFresh(Object.fromEntries(rows.map((r) => [r.module, r]))),
      )
      .catch(() => setFresh({}));
  }, []);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
      <h1>US Money Flow Tracker</h1>
      <p style={{ color: "#666" }}>
        美股资金追踪 · 日频 T+1 · 数据截至美东时间
      </p>
      <div style={{ display: "grid", gap: 16 }}>
        <ExposurePanel freshness={fresh["m2"] ?? null} />
        {MODULES.map((m) => (
          <Panel
            key={m.key}
            title={m.title}
            module={m.key}
            freshness={fresh[m.key] ?? null}
          >
            <p style={{ color: "#999" }}>{m.phase} 建设中</p>
          </Panel>
        ))}
      </div>
    </main>
  );
}
