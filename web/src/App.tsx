import { useEffect, useState } from "react";
import { Panel } from "./components/Panel";
import { ExposurePanel } from "./components/ExposurePanel";
import { MomentumPanel } from "./components/MomentumPanel";
import { LangToggle, useLang } from "./i18n/LangContext";
import { apiGet } from "./api/client";
import type { Freshness } from "./api/types";

// v1 modules (M1 cut per user decision 2026-10-01, option D).
const MODULES = [
  { key: "m4", phase: "Phase 3" },
  { key: "m5", phase: "Phase 4" },
] as const;

export function App() {
  const { t } = useLang();
  const [fresh, setFresh] = useState<Record<string, Freshness | null>>({});

  useEffect(() => {
    apiGet<Freshness[]>("/freshness")
      .then((rows) =>
        setFresh(Object.fromEntries(rows.map((r) => [r.module, r]))),
      )
      .catch(() => setFresh({}));
  }, []);

  const moduleTitle = (key: string) =>
    key === "m4" ? t((d) => d.modules.m4) : t((d) => d.modules.m5);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <h1 style={{ margin: 0 }}>{t((d) => d.app.title)}</h1>
        <LangToggle />
      </div>
      <p style={{ color: "#666" }}>{t((d) => d.app.subtitle)}</p>
      <div style={{ display: "grid", gap: 16 }}>
        <ExposurePanel freshness={fresh["m2"] ?? null} />
        <MomentumPanel freshness={fresh["m3"] ?? null} />
        {MODULES.map((m) => (
          <Panel
            key={m.key}
            title={moduleTitle(m.key)}
            module={m.key}
            freshness={fresh[m.key] ?? null}
          >
            <p style={{ color: "#999" }}>
              {t((d) => d.app.phaseComing, { phase: m.phase })}
            </p>
          </Panel>
        ))}
      </div>
    </main>
  );
}
