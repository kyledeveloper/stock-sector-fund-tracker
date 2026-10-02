import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import { useLang } from "../i18n/LangContext";
import type { Freshness, StockExposure } from "../api/types";

/** Escape upstream strings before injecting into ECharts HTML tooltips. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * M2 panel: cross-sector holdings exposure snapshot (v1 redefined).
 * Mandatory copy: holdings snapshot, NOT a fund flow. Weight changes
 * are mostly price moves. Never 主力/聪明钱.
 */
export function ExposurePanel({ freshness }: { freshness: Freshness | null }) {
  const { t } = useLang();
  const [rows, setRows] = useState<StockExposure[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet<StockExposure[]>("/exposure?limit=15")
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!chartRef.current || !rows) return;
    const chart = echarts.init(chartRef.current);
    const top = [...rows].reverse();
    chart.setOption({
      grid: { left: 70, right: 30, top: 10, bottom: 30 },
      xAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      },
      yAxis: { type: "category", data: top.map((r) => r.ticker) },
      tooltip: {
        trigger: "item",
        formatter: (p: { dataIndex: number }) => {
          const r = top[p.dataIndex];
          // Tickers come from an upstream file; escape before injecting
          // into the HTML tooltip string (red-team M3).
          const ticker = escapeHtml(r.ticker);
          const etfs = r.contributing_etfs.map(escapeHtml).join(", ");
          const weight = t((d) => d.m2.tooltipWeight, {
            w: `${(r.total_weight * 100).toFixed(2)}%`,
          });
          const etfLine = `${t((d) => d.m2.tooltipEtfs, { n: r.etf_count })}: ${etfs}`;
          return `${ticker}<br/>${weight}<br/>${etfLine}`;
        },
      },
      series: [
        {
          type: "bar",
          data: top.map((r) => r.total_weight),
          itemStyle: { color: "#2f6fed" },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [rows, t]);

  return (
    <Panel
      title={t((d) => d.m2.title)}
      module="m2"
      freshness={freshness}
      hasData={rows !== null && rows.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        {t((d) => d.m2.desc)}
      </p>
      {error && (
        <p style={{ color: "#c00" }}>{t((d) => d.common.loadFailed, { error })}</p>
      )}
      {!error && !rows && <p style={{ color: "#999" }}>{t((d) => d.common.loading)}</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: "#999" }}>{t((d) => d.m2.noData)}</p>
      )}
      <div ref={chartRef} style={{ height: 420 }} />
    </Panel>
  );
}
