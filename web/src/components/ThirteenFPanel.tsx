import { useEffect, useState } from "react";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import { useLang } from "../i18n/LangContext";
import type { Freshness, ManagerPositionsView } from "../api/types";

/** Shorten EDGAR registered names for tabs: "Scion Asset Management, LLC" -> "Scion Asset Management". */
function shortName(name: string): string {
  return name
    .replace(/,\s*(LLC|L\.P\.|LP|Inc\.|Corp\.)(\/MA)?$/i, "")
    .replace(/\s+(LLC|L\.P\.|LP)$/i, "")
    .trim();
}

const STATUS_COLOR: Record<string, string> = {
  new: "#1a9e54",
  increased: "#1a9e54",
  decreased: "#d64545",
  unchanged: "#999",
};

function fmtM(v: number): string {
  return `$${(v / 1e6).toFixed(1)}M`;
}

/**
 * M4 panel (13F half): latest quarterly 13F top positions per watchlist
 * manager, with quarter-over-quarter status badges. ~45-day lag is
 * labeled per manager; issuer names shown (no ticker mapping in v1).
 */
export function ThirteenFPanel({ freshness }: { freshness: Freshness | null }) {
  const { t } = useLang();
  const [data, setData] = useState<ManagerPositionsView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState(0);

  useEffect(() => {
    apiGet<ManagerPositionsView[]>("/filings/13f?top_n=15")
      .then((rows) => {
        setData(rows);
        setSel(0);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const statusLabel = (s: string) => {
    switch (s) {
      case "new":
        return t((d) => d.m4.statusNew);
      case "increased":
        return t((d) => d.m4.statusIncreased);
      case "decreased":
        return t((d) => d.m4.statusDecreased);
      default:
        return t((d) => d.m4.statusUnchanged);
    }
  };

  const mgr = data && data.length > 0 ? data[Math.min(sel, data.length - 1)] : null;

  return (
    <Panel
      title={t((d) => d.m4.f13Title)}
      module="m4"
      freshness={freshness}
      hasData={data !== null && data.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        {t((d) => d.m4.f13Desc)}
      </p>
      {error && (
        <p style={{ color: "#c00" }}>{t((d) => d.common.loadFailed, { error })}</p>
      )}
      {!error && !data && <p style={{ color: "#999" }}>{t((d) => d.common.loading)}</p>}
      {!error && data && data.length === 0 && (
        <p style={{ color: "#999" }}>{t((d) => d.m4.noData)}</p>
      )}
      {mgr && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {data!.map((m, i) => (
              <button
                key={m.cik}
                onClick={() => setSel(i)}
                style={{
                  fontSize: 12,
                  padding: "4px 10px",
                  borderRadius: 6,
                  border: "1px solid #ccc",
                  background: i === sel ? "#2f6fed" : "#fff",
                  color: i === sel ? "#fff" : "#333",
                  cursor: "pointer",
                }}
              >
                {shortName(m.filer_name)}
              </button>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "#666", margin: "0 0 8px" }}>
            {t((d) => d.m4.reportDate)} {mgr.report_date} ·{" "}
            {t((d) => d.m4.filedAt)} {mgr.filed_at}
          </p>
          {!mgr.has_previous_quarter && (
            <p
              style={{
                fontSize: 12,
                color: "#8a6d1b",
                background: "#fef6e0",
                borderRadius: 4,
                padding: "6px 10px",
                margin: "0 0 8px",
              }}
            >
              {t((d) => d.m4.firstQuarterNote)}
            </p>
          )}
          <table
            style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: "#888" }}>
                <th>{t((d) => d.m4.colIssuer)}</th>
                <th style={{ textAlign: "right" }}>{t((d) => d.m4.colValue)}</th>
                <th style={{ textAlign: "right" }}>{t((d) => d.m4.colShares)}</th>
                <th style={{ textAlign: "right" }}>{t((d) => d.m4.colChange)}</th>
              </tr>
            </thead>
            <tbody>
              {mgr.positions.map((p) => (
                <tr
                  key={`${p.cusip}-${p.put_call}`}
                  style={{ borderTop: "1px solid #eee" }}
                >
                  <td>
                    {p.issuer}
                    {p.put_call && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "#d9930d",
                          marginLeft: 6,
                          border: "1px solid #d9930d",
                          borderRadius: 4,
                          padding: "0 4px",
                        }}
                      >
                        {t((d) => d.m4.optionLeg)} {p.put_call}
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>{fmtM(p.value_usd)}</td>
                  <td style={{ textAlign: "right" }}>{p.shares.toLocaleString()}</td>
                  <td
                    style={{
                      textAlign: "right",
                      color: STATUS_COLOR[p.status] ?? "#333",
                      fontWeight: 600,
                    }}
                  >
                    {statusLabel(p.status)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {mgr.exited_count > 0 && (
            <p style={{ fontSize: 12, color: "#999", marginTop: 8 }}>
              {t((d) => d.m4.exitedLine, { n: mgr.exited_count })}
            </p>
          )}
        </>
      )}
    </Panel>
  );
}
