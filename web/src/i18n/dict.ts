/**
 * Bilingual dictionaries (zh / en). Zero-dependency i18n.
 *
 * `en` is typed as `Dict` (= typeof zh), so a missing or misshapen
 * English key is a *compile* error, not a runtime surprise. All UI copy
 * must come from here -- no hardcoded Chinese/English in components.
 * Placeholders use {name} and are filled by `format` in LangContext.
 */
export const zh = {
  app: {
    title: "US Money Flow Tracker",
    subtitle: "美股资金追踪 · 日频 T+1 · 数据截至美东时间",
    phaseComing: "{phase} 建设中",
  },
  modules: {
    m4: "聪明钱（13F / 内幕）",
    m5: "期权情绪",
  },
  panel: {
    asOf: "截至 {date}（美东）",
    freshnessUnknown: "新鲜度未知",
    noData: "暂无数据",
    stale: "已过期",
  },
  common: {
    loading: "加载中…",
    loadFailed: "加载失败：{error}",
  },
  m2: {
    title: "持仓敞口快照",
    // Mandatory wording contract (PLAN.md): holdings snapshot, NOT a fund
    // flow; weight day-changes are mostly price moves. The English text
    // carries the same meaning, not a literal translation.
    desc: "SSGA 官方日持仓 → 个股跨板块权重汇总。持仓快照，非资金流；权重日变化主要来自价格波动。",
    noData: "暂无数据（等待每日 pipeline 运行）",
    tooltipWeight: "权重 {w}",
    tooltipEtfs: "{n} 只板块ETF",
  },
  m3: {
    title: "板块动量 / 轮动",
    desc: "11 只板块 ETF vs SPY 的 20/60 日超额收益（Yahoo 日线，复权收盘）。价格动量信号，非资金流；简化 RRG 四象限仅作轮动参考。",
    noData:
      "暂无数据（先运行回填：python -m moneyflow.pipeline.daily backfill-m3）",
    axisX: "60日超额收益 vs SPY",
    axisY: "20日超额收益 vs SPY",
    tableSector: "板块",
    tableD20: "20日超额",
    tableD60: "60日超额",
    tableQuadrant: "象限",
    tooltipD20: "20日 {v}",
    tooltipD60: "60日 {v}",
    quadrant: {
      leading: "领涨",
      weakening: "走弱",
      lagging: "落后",
      improving: "改善",
    },
  },
};

export type Dict = typeof zh;

export const en: Dict = {
  app: {
    title: "US Money Flow Tracker",
    subtitle: "US equity money-flow tracking · daily T+1 · data as of ET",
    phaseComing: "Coming in {phase}",
  },
  modules: {
    m4: "Smart Money (13F / Insider)",
    m5: "Options Sentiment",
  },
  panel: {
    asOf: "as of {date} ET",
    freshnessUnknown: "freshness unknown",
    noData: "no data yet",
    stale: "STALE",
  },
  common: {
    loading: "Loading…",
    loadFailed: "Failed to load: {error}",
  },
  m2: {
    title: "Holdings Exposure Snapshot",
    desc: "SSGA official daily holdings → cross-sector weight aggregation per stock. Holdings snapshot, not fund flow; day-to-day weight changes are mostly price moves.",
    noData: "No data yet (waiting for the daily pipeline run)",
    tooltipWeight: "Weight {w}",
    tooltipEtfs: "{n} sector ETFs",
  },
  m3: {
    title: "Sector Momentum / Rotation",
    desc: "20/60-day excess returns vs SPY for 11 sector ETFs (Yahoo daily bars, adjusted close). Price-momentum signal, not fund flow; the simplified RRG quadrants are for rotation reference only.",
    noData:
      "No data yet (run the backfill first: python -m moneyflow.pipeline.daily backfill-m3)",
    axisX: "60d excess return vs SPY",
    axisY: "20d excess return vs SPY",
    tableSector: "Sector",
    tableD20: "20d excess",
    tableD60: "60d excess",
    tableQuadrant: "Quadrant",
    tooltipD20: "20d {v}",
    tooltipD60: "60d {v}",
    quadrant: {
      leading: "Leading",
      weakening: "Weakening",
      lagging: "Lagging",
      improving: "Improving",
    },
  },
};
