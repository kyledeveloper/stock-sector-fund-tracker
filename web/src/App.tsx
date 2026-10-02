import { useEffect, useState } from "react";
import { ExposurePanel } from "./components/ExposurePanel";
import { Form4Panel } from "./components/Form4Panel";
import { MomentumPanel } from "./components/MomentumPanel";
import { PutCallPanel } from "./components/PutCallPanel";
import { ThirteenFPanel } from "./components/ThirteenFPanel";
import { LangToggle, useLang } from "./i18n/LangContext";
import { apiGet } from "./api/client";
import type { Freshness } from "./api/types";

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
        <ThirteenFPanel freshness={fresh["m4"] ?? null} />
        <Form4Panel freshness={fresh["m4"] ?? null} />
        <PutCallPanel freshness={fresh["m5"] ?? null} />
      </div>
    </main>
  );
}
