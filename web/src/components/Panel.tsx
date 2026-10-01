import type { ReactNode } from "react";
import type { Freshness } from "../api/types";

interface Props {
  title: string;
  module: Freshness["module"];
  freshness: Freshness | null;
  children: ReactNode;
}

/**
 * Panel shell. Enforces the freshness contract from PLAN.md:
 * every panel shows "as of [ET date]"; stale panels render grayed out
 * with a warning instead of silently showing old data.
 */
export function Panel({ title, freshness, children }: Props) {
  const stale = freshness?.stale ?? false;
  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        opacity: stale ? 0.45 : 1,
        background: stale ? "#f6f6f6" : "#fff",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
        <span style={{ fontSize: 12, color: "#666" }}>
          {freshness?.as_of ? `as of ${freshness.as_of} ET` : "no data yet"}
          {stale && " · STALE"}
        </span>
      </header>
      {children}
    </section>
  );
}
