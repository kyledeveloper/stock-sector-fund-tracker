import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import { useLang } from "../i18n/LangContext";
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

const QUADRANT_COLOR: Record<string, string> = {
  leading: "#1a9e54",
  weakening: "#d9930d",
  lagging: "#d64545",
  improving: "#2f6fed",
};

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

/**
 * M3 panel: sector momentum vs SPY (simplified RRG).
 * x = 60d excess return, y = 20d excess return. Price momentum, NOT a fund flow.
 * EOD source: Yahoo chart (adjusted close), T+1.
 */
export function MomentumPanel({ freshness }: { freshness: Freshness | null }) {
  const { t } = useLang();
  const [rows, setRows] = useState<SectorMomentum[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  const quadrantLabel = (q: string) => {
    switch (q) {
      case "leading":
        return t((d) => d.m3.quadrant.leading);
      case "weakening":
        return t((d) => d.m3.quadrant.weakening);
      case "lagging":
        return t((d) => d.m3.quadrant.lagging);
      case "improving":
        return t((d) => d.m3.quadrant.improving);
      default:
        return q;
    }
  };

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
        name: t((d) => d.m3.axisX),
        nameLocation: "middle",
        nameGap: 28,
        min: pad(xs)[0],
        max: pad(xs)[1],
        axisLabel: { formatter: (v: number) => pct(v) },
      },
      yAxis: {
        type: "value",
        name: t((d) => d.m3.axisY),
        min: pad(ys)[0],
        max: pad(ys)[1],
        axisLabel: { formatter: (v: number) => pct(v) },
      },
      tooltip: {
        trigger: "item",
        formatter: (p: { dataIndex: number }) => {
          const r = rows[p.dataIndex];
          const ticker = escapeHtml(r.ticker);
          const q = escapeHtml(quadrantLabel(r.rrg_quadrant));
          const d20 = t((d) => d.m3.tooltipD20, { v: pct(r.rs_20d) });
          const d60 = t((d) => d.m3.tooltipD60, { v: pct(r.rs_60d) });
          return `${ticker}（${q}）<br/>${d20}<br/>${d60}`;
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
        {
          type: "text",
          right: 40,
          top: 40,
          style: {
            text: quadrantLabel("leading"),
            fill: QUADRANT_COLOR.leading,
            fontSize: 12,
          },
        },
        {
          type: "text",
          left: 70,
          top: 40,
          style: {
            text: quadrantLabel("improving"),
            fill: QUADRANT_COLOR.improving,
            fontSize: 12,
          },
        },
        {
          type: "text",
          right: 40,
          bottom: 50,
          style: {
            text: quadrantLabel("weakening"),
            fill: QUADRANT_COLOR.weakening,
            fontSize: 12,
          },
        },
        {
          type: "text",
          left: 70,
          bottom: 50,
          style: {
            text: quadrantLabel("lagging"),
            fill: QUADRANT_COLOR.lagging,
            fontSize: 12,
          },
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
      title={t((d) => d.m3.title)}
      module="m3"
      freshness={freshness}
      hasData={rows !== null && rows.length > 0}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        {t((d) => d.m3.desc)}
      </p>
      {error && (
        <p style={{ color: "#c00" }}>{t((d) => d.common.loadFailed, { error })}</p>
      )}
      {!error && !rows && <p style={{ color: "#999" }}>{t((d) => d.common.loading)}</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: "#999" }}>{t((d) => d.m3.noData)}</p>
      )}
      {rows && rows.length > 0 && (
        <>
          <div ref={chartRef} style={{ height: 420 }} />
          <table
            style={{
              width: "100%",
              fontSize: 13,
              borderCollapse: "collapse",
              marginTop: 8,
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: "#888" }}>
                <th>{t((d) => d.m3.tableSector)}</th>
                <th>{t((d) => d.m3.tableD20)}</th>
                <th>{t((d) => d.m3.tableD60)}</th>
                <th>{t((d) => d.m3.tableQuadrant)}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} style={{ borderTop: "1px solid #eee" }}>
                  <td style={{ fontWeight: 600 }}>{r.ticker}</td>
                  <td style={{ color: r.rs_20d >= 0 ? "#1a9e54" : "#d64545" }}>
                    {pct(r.rs_20d)}
                  </td>
                  <td style={{ color: r.rs_60d >= 0 ? "#1a9e54" : "#d64545" }}>
                    {pct(r.rs_60d)}
                  </td>
                  <td>{quadrantLabel(r.rrg_quadrant)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  );
}
