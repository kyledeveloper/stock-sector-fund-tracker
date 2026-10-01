import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
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
export function ExposurePanel({ freshness }: { freshness: Freshness | null }) {  const [rows, setRows] = useState<StockExposure[] | null>(null);
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
          const t = escapeHtml(r.ticker);
          const etfs = r.contributing_etfs.map(escapeHtml).join(", ");
          return `${t}<br/>权重 ${(r.total_weight * 100).toFixed(2)}%<br/>${r.etf_count} 只板块ETF: ${etfs}`;
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
  }, [rows]);

  return (
    <Panel
      title="持仓敞口快照"
      module="m2"
      freshness={freshness}
      hasData={rows !== null && rows.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        SSGA 官方日持仓 → 个股跨板块权重汇总。持仓快照，非资金流；权重日变化主要来自价格波动。
      </p>
      {error && <p style={{ color: "#c00" }}>加载失败：{error}</p>}
      {!error && !rows && <p style={{ color: "#999" }}>加载中…</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: "#999" }}>暂无数据（等待每日 pipeline 运行）</p>
      )}
      <div ref={chartRef} style={{ height: 420 }} />
    </Panel>
  );
}
