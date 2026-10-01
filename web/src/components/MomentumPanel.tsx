import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import type { Freshness, SectorMomentum } from "../api/types";

/** Escape upstream strings before injecting into ECharts HTML tooltips. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const QUADRANT_CN: Record<string, string> = {
  leading: "领涨",
  weakening: "走弱",
  lagging: "落后",
  improving: "改善",
};

const QUADRANT_COLOR: Record<string, string> = {
  leading: "#1a9e54",
  weakening: "#d9930d",
  lagging: "#d64545",
  improving: "#2f6fed",
};

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

/**
 * M3 panel: sector momentum vs SPY (simplified RRG).
 * x = 60日超额收益, y = 20日超额收益. Price momentum, NOT a fund flow.
 * EOD source: Yahoo chart (adjusted close), T+1.
 */
export function MomentumPanel({ freshness }: { freshness: Freshness | null }) {
  const [rows, setRows] = useState<SectorMomentum[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet<SectorMomentum[]>("/momentum")
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!chartRef.current || !rows || rows.length === 0) return;
    const chart = echarts.init(chartRef.current);
    const xs = rows.map((r) => r.rs_60d);
    const ys = rows.map((r) => r.rs_20d);
    const pad = (vals: number[]) => {
      const m = Math.max(...vals.map(Math.abs), 0.01);
      return [-m * 1.15, m * 1.15];
    };
    chart.setOption({
      grid: { left: 60, right: 30, top: 30, bottom: 40 },
      xAxis: {
        type: "value",
        name: "60日超额收益 vs SPY",
        nameLocation: "middle",
        nameGap: 28,
        min: pad(xs)[0],
        max: pad(xs)[1],
        axisLabel: { formatter: (v: number) => pct(v) },
      },
      yAxis: {
        type: "value",
        name: "20日超额收益 vs SPY",
        min: pad(ys)[0],
        max: pad(ys)[1],
        axisLabel: { formatter: (v: number) => pct(v) },
      },
      tooltip: {
        trigger: "item",
        formatter: (p: { dataIndex: number }) => {
          const r = rows[p.dataIndex];
          const t = escapeHtml(r.ticker);
          const q = escapeHtml(QUADRANT_CN[r.rrg_quadrant] ?? r.rrg_quadrant);
          return `${t}（${q}）<br/>20日 ${pct(r.rs_20d)}<br/>60日 ${pct(r.rs_60d)}`;
        },
      },
      series: [
        {
          type: "scatter",
          symbolSize: 22,
          data: rows.map((r) => ({
            value: [r.rs_60d, r.rs_20d],
            itemStyle: { color: QUADRANT_COLOR[r.rrg_quadrant] ?? "#888" },
          })),
          label: {
            show: true,
            formatter: (p: { dataIndex: number }) => rows[p.dataIndex].ticker,
            position: "top",
            fontSize: 10,
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#bbb", type: "dashed" },
            data: [{ xAxis: 0 }, { yAxis: 0 }],
          },
        },
      ],
      graphic: [
        { type: "text", right: 40, top: 40, style: { text: "领涨", fill: "#1a9e54", fontSize: 12 } },
        { type: "text", left: 70, top: 40, style: { text: "改善", fill: "#2f6fed", fontSize: 12 } },
        { type: "text", right: 40, bottom: 50, style: { text: "走弱", fill: "#d9930d", fontSize: 12 } },
        { type: "text", left: 70, bottom: 50, style: { text: "落后", fill: "#d64545", fontSize: 12 } },
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
      title="板块动量 / 轮动"
      module="m3"
      freshness={freshness}
      hasData={rows !== null && rows.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        11 只板块 ETF vs SPY 的 20/60 日超额收益（Yahoo 日线，复权收盘）。价格动量信号，非资金流；简化 RRG
        四象限仅作轮动参考。
      </p>
      {error && <p style={{ color: "#c00" }}>加载失败：{error}</p>}
      {!error && !rows && <p style={{ color: "#999" }}>加载中…</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: "#999" }}>暂无数据（先运行回填：python -m moneyflow.pipeline.daily backfill-m3）</p>
      )}
      {rows && rows.length > 0 && (
        <>
          <div ref={chartRef} style={{ height: 420 }} />
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#888" }}>
                <th>板块</th>
                <th>20日超额</th>
                <th>60日超额</th>
                <th>象限</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} style={{ borderTop: "1px solid #eee" }}>
                  <td style={{ fontWeight: 600 }}>{r.ticker}</td>
                  <td style={{ color: r.rs_20d >= 0 ? "#1a9e54" : "#d64545" }}>{pct(r.rs_20d)}</td>
                  <td style={{ color: r.rs_60d >= 0 ? "#1a9e54" : "#d64545" }}>{pct(r.rs_60d)}</td>
                  <td>{QUADRANT_CN[r.rrg_quadrant] ?? r.rrg_quadrant}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  );
}
