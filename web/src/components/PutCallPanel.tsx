import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import { Panel } from "./Panel";
import { apiGet } from "../api/client";
import { useLang } from "../i18n/LangContext";
import type { Freshness, PutCallPoint, PutCallSeries } from "../api/types";

const TOTAL_COLOR = "#2f6fed";
const EQUITY_COLOR = "#d9930d";

/** Finite numbers only -- null/missing values must never be plotted as 0. */
function numOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * M5 panel: CBOE total + equity put/call ratios, 90-day line chart.
 * Options-market sentiment, NOT fund flow, NOT a forecast. T+1.
 */
export function PutCallPanel({ freshness }: { freshness: Freshness | null }) {
  const { t } = useLang();
  const [series, setSeries] = useState<PutCallSeries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  // Null-safe: drop rows with no usable date or no finite ratio.
  const rows = useMemo<PutCallPoint[]>(
    () =>
      (series?.data ?? []).filter(
        (p) =>
          typeof p?.date === "string" &&
          p.date.length > 0 &&
          (numOrNull(p.total_put_call) !== null ||
            numOrNull(p.equity_put_call) !== null),
      ),
    [series],
  );
  const hasData = rows.length > 0;

  useEffect(() => {
    apiGet<PutCallSeries>("/sentiment/putcall?days=90")
      .then(setSeries)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!chartRef.current || !hasData) return;
    const totalName = t((d) => d.m5.legendTotal);
    const equityName = t((d) => d.m5.legendEquity);
    const chart = echarts.init(chartRef.current);
    // Missing points stay null -> line breaks (gap), never 0.
    const totalData = rows.map((p) => numOrNull(p.total_put_call));
    const equityData = rows.map((p) => numOrNull(p.equity_put_call));
    chart.setOption({
      grid: { left: 56, right: 30, top: 40, bottom: 44 },
      legend: { data: [totalName, equityName], top: 0 },
      xAxis: {
        type: "category",
        data: rows.map((p) => p.date),
        axisLabel: { fontSize: 10 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          formatter: (v: number) => v.toFixed(2),
        },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number | null) =>
          v == null ? "—" : v.toFixed(2),
      },
      series: [
        {
          name: totalName,
          type: "line",
          data: totalData,
          itemStyle: { color: TOTAL_COLOR },
          lineStyle: { color: TOTAL_COLOR },
          showSymbol: false,
          connectNulls: false,
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#999", type: "dashed" },
            label: { formatter: t((d) => d.m5.refLine) },
            data: [{ yAxis: 0.7 }],
          },
        },
        {
          name: equityName,
          type: "line",
          data: equityData,
          itemStyle: { color: EQUITY_COLOR },
          lineStyle: { color: EQUITY_COLOR },
          showSymbol: false,
          connectNulls: false,
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [rows, hasData, t]);

  return (
    <Panel
      title={t((d) => d.m5.title)}
      module="m5"
      freshness={freshness}
      hasData={hasData}
    >
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        {t((d) => d.m5.desc)}
      </p>
      {error && (
        <p style={{ color: "#c00" }}>{t((d) => d.common.loadFailed, { error })}</p>
      )}
      {!error && !series && (
        <p style={{ color: "#999" }}>{t((d) => d.common.loading)}</p>
      )}
      {!error && series && !hasData && (
        <p style={{ color: "#999" }}>{t((d) => d.m5.noData)}</p>
      )}
      {hasData && <div ref={chartRef} style={{ height: 360 }} />}
    </Panel>
  );
}
