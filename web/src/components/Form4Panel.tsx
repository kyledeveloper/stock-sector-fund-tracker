import { useEffect, useState } from "react";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import { useLang } from "../i18n/LangContext";
import type { Freshness, InsiderBuyView } from "../api/types";

function fmtMoney(v: number | null): string {
  if (v === null) return "—";
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${(v / 1e3).toFixed(0)}K`;
}

/**
 * M4 panel (Form 4 half): officer/director open-market buys from the
 * market-wide daily scan, newest first (ranked by value within each day).
 * ~2-day disclosure lag. 10b5-1 plan trades are flagged (weaker signal);
 * 4/A amendments are flagged (corrected values may appear as extra rows).
 * Non-derivative transactions only in v1.
 */
export function Form4Panel({ freshness }: { freshness: Freshness | null }) {
  const { t } = useLang();
  const [rows, setRows] = useState<InsiderBuyView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<InsiderBuyView[]>("/filings/form4?limit=50")
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <Panel
      title={t((d) => d.m4.f4Title)}
      module="m4"
      freshness={freshness}
      hasData={rows !== null && rows.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        {t((d) => d.m4.f4Desc)}
      </p>
      {error && (
        <p style={{ color: "#c00" }}>{t((d) => d.common.loadFailed, { error })}</p>
      )}
      {!error && !rows && <p style={{ color: "#999" }}>{t((d) => d.common.loading)}</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: "#999" }}>{t((d) => d.m4.noData)}</p>
      )}
      {rows && rows.length > 0 && (
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#888" }}>
              <th>{t((d) => d.m4.f4ColTicker)}</th>
              <th>{t((d) => d.m4.f4ColInsider)}</th>
              <th>{t((d) => d.m4.f4ColDate)}</th>
              <th>{t((d) => d.m4.f4ColFiled)}</th>
              <th style={{ textAlign: "right" }}>{t((d) => d.m4.f4ColShares)}</th>
              <th style={{ textAlign: "right" }}>{t((d) => d.m4.f4ColPrice)}</th>
              <th style={{ textAlign: "right" }}>{t((d) => d.m4.f4ColValue)}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={`${r.ticker}-${r.insider}-${r.transaction_date}-${i}`}
                style={{ borderTop: "1px solid #eee" }}
              >
                <td style={{ fontWeight: 600 }}>{r.ticker}</td>
                <td>
                  {r.insider}
                  {r.officer_title && (
                    <span style={{ color: "#999", fontSize: 11, marginLeft: 6 }}>
                      {r.officer_title}
                    </span>
                  )}
                  {r.is_joint_filing && (
                    <span style={{ color: "#999", fontSize: 11, marginLeft: 6 }}>
                      {t((d) => d.m4.f4Joint)}
                    </span>
                  )}
                  {r.is_amendment && (
                    <span
                      style={{
                        fontSize: 11,
                        color: "#7a5af8",
                        marginLeft: 6,
                        border: "1px solid #7a5af8",
                        borderRadius: 4,
                        padding: "0 4px",
                      }}
                    >
                      {t((d) => d.m4.f4Amendment)}
                    </span>
                  )}
                  {r.is_10b5_1 && (
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
                      {t((d) => d.m4.f4Plan)}
                    </span>
                  )}
                </td>
                <td>{r.transaction_date}</td>
                <td style={{ color: "#999" }}>{r.filed_at}</td>
                <td style={{ textAlign: "right" }}>{r.shares.toLocaleString()}</td>
                <td style={{ textAlign: "right" }}>
                  {r.price === null ? "—" : `$${r.price.toFixed(2)}`}
                </td>
                <td
                  style={{
                    textAlign: "right",
                    color: "#1a9e54",
                    fontWeight: 600,
                  }}
                >
                  {fmtMoney(r.value_usd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
