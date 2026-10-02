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
    m4: "机构与内幕（13F / Form 4）",
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
  m4: {
    f13Title: "13F 持仓 · 机构观察名单",
    f13Desc:
      "12 家机构最新季度 13F 持仓 Top 15。季度披露，滞后约45天；仅多头持仓，不含空头与现金；无 ticker 映射，显示发行人名称。",
    reportDate: "报告期",
    filedAt: "披露日",
    colIssuer: "发行人",
    colValue: "市值",
    colShares: "股数",
    colChange: "环比",
    statusNew: "新建仓",
    statusIncreased: "加仓",
    statusDecreased: "减仓",
    statusUnchanged: "不变",
    exitedLine: "本季清仓 {n} 只",
    optionLeg: "期权",
    noData:
      "暂无数据（先运行回填：python -m moneyflow.pipeline.daily backfill-m4）",
    f4Title: "Form 4 内幕人买入",
    f4Desc:
      "高管 / 董事的公开市场买入（全市场每日扫描；按时间倒序，同日内按金额排序）。约 2 天披露滞后；10b5-1 计划内交易已标注——计划内买入通常信号较弱。仅含非衍生品交易；4/A 修正案已标注为“修正”，其更正后的金额可能以单独行出现。",
    f4ColTicker: "代码",
    f4ColInsider: "内幕人",
    f4ColDate: "交易日",
    f4ColFiled: "披露日",
    f4ColShares: "股数",
    f4ColPrice: "价格",
    f4ColValue: "金额",
    f4Plan: "10b5-1",
    f4Amendment: "修正",
    f4Joint: "联合申报",
    firstQuarterNote:
      "注意：这是该机构入库的首个季度，所有持仓都标记为“新建仓”；环比变化自下个季度起生效。",
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
    m4: "Institutions & Insiders (13F / Form 4)",
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
  m4: {
    f13Title: "13F Holdings · Manager Watchlist",
    f13Desc:
      "Top-15 positions from the latest quarterly 13F of 12 managers. Quarterly filings with ~45-day lag; long positions only, no shorts or cash; issuer names shown (no ticker mapping in v1).",
    reportDate: "Report date",
    filedAt: "Filed",
    colIssuer: "Issuer",
    colValue: "Value",
    colShares: "Shares",
    colChange: "QoQ",
    statusNew: "New",
    statusIncreased: "Added",
    statusDecreased: "Trimmed",
    statusUnchanged: "Unchanged",
    exitedLine: "{n} exited this quarter",
    optionLeg: "Option",
    noData:
      "No data yet (run the backfill first: python -m moneyflow.pipeline.daily backfill-m4)",
    f4Title: "Form 4 Insider Buys",
    f4Desc:
      "Open-market buys by officers / directors (market-wide daily scan; newest first, ranked by value within each day). ~2-day disclosure lag; 10b5-1 plan trades are flagged -- in-plan buys are usually weaker signals. Non-derivative transactions only; 4/A amendments are flagged as amended, and their corrected values may appear as separate rows.",
    f4ColTicker: "Ticker",
    f4ColInsider: "Insider",
    f4ColDate: "Trade date",
    f4ColFiled: "Filed",
    f4ColShares: "Shares",
    f4ColPrice: "Price",
    f4ColValue: "Value",
    f4Plan: "10b5-1",
    f4Amendment: "Amended",
    f4Joint: "Joint filing",
    firstQuarterNote:
      "Note: this is the first quarter on file for this manager, so every position is badged “new”; quarter-over-quarter changes take effect from next quarter.",
  },
};
