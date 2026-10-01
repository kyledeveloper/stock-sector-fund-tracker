import { useEffect, useState } from "react";
import { Panel } from "./components/Panel";
import { apiGet } from "./api/client";
import type { Freshness } from "./api/types";

const MODULES = [
  { key: "m1", title: "板块资金流", phase: "Phase 1" },
  { key: "m2", title: "配置型资金敞口（估算）", phase: "Phase 2" },
  { key: "m3", title: "板块动量 / 轮动", phase: "Phase 3" },
  { key: "m4", title: "聪明钱（13F / 内幕）", phase: "Phase 4" },
  { key: "m5", title: "期权情绪", phase: "Phase 5" },
] as const;

export function App() {
  const [fresh, setFresh] = useState<Record<string, Freshness | null>>({});

  useEffect(() => {
    // Freshness endpoint lands in Phase 1; tolerate absence until then.
    apiGet<Freshness[]>("/freshness")
      .then((rows) =>
        setFresh(Object.fromEntries(rows.map((r) => [r.module, r])))
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
