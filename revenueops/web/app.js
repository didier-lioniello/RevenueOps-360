"use strict";

const reportNode = document.getElementById("report-data");
const report = JSON.parse(reportNode.content.textContent);

if (report.dataset.synthetic !== true) {
  throw new Error("RevenueOps-360 requires an explicit synthetic-data attestation.");
}

const metrics = report.metrics;
const currencyCode = report.dataset.currency;
const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: currencyCode,
  maximumFractionDigits: 0,
});
const numberFormatter = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

const money = (value) => (value == null ? "n/a" : moneyFormatter.format(value));
const percent = (value) => (value == null ? "n/a" : `${(value * 100).toFixed(1)}%`);
const ratio = (value) => (value == null ? "n/a" : `${Number(value).toFixed(2)}×`);
const days = (value) => (value == null ? "n/a" : `${numberFormatter.format(value)}d`);
const months = (value) => (value == null ? "n/a" : `${numberFormatter.format(value)} mo`);
const text = (tag, content, className) => {
  const element = document.createElement(tag);
  element.textContent = content;
  if (className) element.className = className;
  return element;
};

document.getElementById("period").textContent =
  `${report.dataset.period_start} → ${report.dataset.period_end}`;
document.getElementById("dataset-label").textContent = report.dataset.label;
document.getElementById("target").textContent = money(metrics.forecast.target);

const kpis = [
  {
    label: "Closed-won",
    value: money(metrics.sales.closed_won_revenue),
    note: `${metrics.sales.won_deals} synthetic wins`,
    tone: "teal",
  },
  {
    label: "Weighted forecast",
    value: money(metrics.forecast.weighted),
    note: `${percent(metrics.forecast.attainment.weighted)} of target`,
    tone: "blue",
  },
  {
    label: "Pipeline coverage",
    value: ratio(metrics.pipeline.coverage),
    note: `configured target ${ratio(metrics.pipeline.coverage_target)}`,
    tone: "coral",
  },
  {
    label: "Win rate",
    value: percent(metrics.sales.win_rate),
    note: "won / closed opportunities",
    tone: "gold",
  },
  {
    label: "ACV",
    value: money(metrics.sales.average_contract_value),
    note: "mean closed-won ACV",
    tone: "teal",
  },
  {
    label: "Sales cycle",
    value: days(metrics.sales.average_sales_cycle_days),
    note: "mean across closed deals",
    tone: "blue",
  },
  {
    label: "CAC payback",
    value: months(metrics.unit_economics.cac_payback_months),
    note: "simplified gross-margin basis",
    tone: "gold",
  },
  {
    label: "LTV:CAC",
    value: ratio(metrics.unit_economics.ltv_to_cac),
    note: "simplified churn model",
    tone: "coral",
  },
];

const scorecard = document.getElementById("scorecard");
kpis.forEach((kpi) => {
  const card = document.createElement("article");
  card.className = `kpi-card tone-${kpi.tone}`;
  const top = document.createElement("div");
  top.className = "kpi-top";
  top.append(text("span", kpi.label), text("span", "", "kpi-dot"));
  card.append(top, text("strong", kpi.value, "kpi-value"), text("span", kpi.note, "kpi-note"));
  scorecard.append(card);
});

const funnelChart = document.getElementById("funnel-chart");
const funnelMax = Math.max(...metrics.funnel.stages.map((stage) => stage.count), 1);
metrics.funnel.stages.forEach((stage, index) => {
  const row = document.createElement("div");
  row.className = "funnel-row";
  const meta = document.createElement("div");
  meta.className = "funnel-meta";
  meta.append(text("span", stage.stage), text("span", numberFormatter.format(stage.count)));
  const progress = document.createElement("progress");
  progress.className = "metric-progress funnel-progress";
  progress.max = funnelMax;
  progress.value = stage.count;
  const footer = document.createElement("div");
  footer.className = "funnel-footer";
  footer.append(
    text(
      "span",
      index === 0 ? "cohort entry" : `${percent(stage.conversion_from_previous)} step conversion`,
      "conversion-chip",
    ),
  );
  row.append(meta, progress, footer);
  funnelChart.append(row);
});

const forecastChart = document.getElementById("forecast-chart");
[
  ["Actual", "actual", "blue"],
  ["Commit", "commit", "teal"],
  ["Best case", "best_case", "gold"],
  ["Weighted", "weighted", "coral"],
].forEach(([label, key, tone]) => {
  const row = document.createElement("div");
  row.className = "forecast-row";
  const meta = document.createElement("div");
  meta.className = "forecast-meta";
  meta.append(text("span", label), text("strong", money(metrics.forecast[key])));
  const track = document.createElement("div");
  track.className = "forecast-track";
  const progress = document.createElement("progress");
  progress.className = `metric-progress forecast-progress forecast-${tone}`;
  progress.max = metrics.forecast.target;
  progress.value = Math.min(metrics.forecast[key], metrics.forecast.target);
  track.append(progress, text("span", "", "forecast-target"));
  row.append(meta, track);
  forecastChart.append(row);
});

const coverageCard = document.getElementById("coverage-card");
const coverage = metrics.pipeline.coverage;
const ring = document.createElement("div");
ring.className = "coverage-ring";
ring.append(text("span", ratio(coverage), "coverage-value"));
const coverageBar = document.createElement("progress");
coverageBar.className = "metric-progress coverage-progress";
coverageBar.max = metrics.pipeline.coverage_target;
coverageBar.value = Math.min(coverage ?? 0, metrics.pipeline.coverage_target);
coverageCard.append(
  ring,
  coverageBar,
  text("p", "In-period coverage vs configured multiple"),
  text("strong", `${money(metrics.pipeline.coverage_gap_amount)} coverage gap`),
  text(
    "p",
    `${money(metrics.pipeline.out_of_period_open_pipeline)} excluded outside the period`,
  ),
);

const channelGrid = document.getElementById("channel-grid");
const maxAttributedRevenue = Math.max(
  ...metrics.marketing.channels.map((channel) => channel.attributed_revenue),
  1,
);
metrics.marketing.channels.forEach((channel) => {
  const card = document.createElement("article");
  card.className = "channel-card";
  const head = document.createElement("div");
  head.className = "channel-head";
  head.append(
    text("h3", channel.channel),
    text(
      "span",
      percent(channel.roi),
      `roi ${channel.roi != null && channel.roi < 0.2 ? "low" : ""}`,
    ),
  );
  const progress = document.createElement("progress");
  progress.className = "metric-progress channel-progress";
  progress.max = maxAttributedRevenue;
  progress.value = channel.attributed_revenue;
  const lines = [
    ["Spend", money(channel.spend)],
    ["Won ACV", money(channel.attributed_revenue)],
    ["Gross profit", money(channel.attributed_gross_profit)],
    ["Won deals", numberFormatter.format(channel.won_deals)],
    ["Channel CAC", money(channel.channel_cac)],
  ];
  if (channel.roi_unavailable_reason) {
    lines.push(["ROI status", channel.roi_unavailable_reason]);
  }
  card.append(head, progress);
  lines.forEach(([label, value]) => {
    const line = document.createElement("div");
    line.className = "metric-line";
    line.append(text("span", label), text("strong", value));
    card.append(line);
  });
  channelGrid.append(card);
});

const scenario = report.scenario;
document.getElementById("scenario-name").textContent = scenario.name;
const scenarioInputs = document.getElementById("scenario-inputs");
[
  ["Conversion", scenario.inputs.conversion_lift_pct],
  ["ACV", scenario.inputs.acv_change_pct],
  ["Cycle", scenario.inputs.cycle_change_pct],
  ["Spend", scenario.inputs.marketing_spend_change_pct],
].forEach(([label, value]) => {
  scenarioInputs.append(text("span", `${label} ${value >= 0 ? "+" : ""}${value}%`));
});

const comparison = document.getElementById("scenario-comparison");
const scenarioRows = [
  ["Modeled revenue", "modeled_revenue", money, false],
  ["Modeled wins", "modeled_wins", numberFormatter.format.bind(numberFormatter), false],
  ["ACV", "acv", money, false],
  ["Sales cycle", "cycle_days", days, true],
  ["Marketing spend", "marketing_spend", money, true],
  ["Sales velocity / day", "sales_velocity_per_day", money, false],
  ["Marketing ROI", "marketing_roi", percent, false],
  ["CAC payback", "cac_payback_months", months, true],
  ["LTV:CAC", "ltv_to_cac", ratio, false],
];
if (!scenario.baseline.available || !scenario.modeled.available) {
  comparison.append(
    text(
      "p",
      scenario.modeled.reason || scenario.baseline.reason || "Scenario unavailable.",
      "scenario-unavailable",
    ),
  );
} else {
  scenarioRows.forEach(([label, key, formatter, lowerIsBetter]) => {
    const row = document.createElement("article");
    row.className = "comparison-row";
    const values = document.createElement("div");
    values.className = "compare-values";
    values.append(
      text("span", formatter(scenario.baseline[key]), "base-value"),
      text("span", "→"),
      text("strong", formatter(scenario.modeled[key]), "modeled-value"),
    );
    const relative = scenario.delta[key].relative_pct;
    const improvement = relative == null || (lowerIsBetter ? relative <= 0 : relative >= 0);
    const deltaText =
      relative == null ? "n/a" : `${relative >= 0 ? "+" : ""}${relative.toFixed(1)}%`;
    row.append(
      text("span", label, "comparison-label"),
      values,
      text("span", `${deltaText} vs baseline`, `delta ${improvement ? "" : "negative"}`),
    );
    comparison.append(row);
  });
}

const recommendationGrid = document.getElementById("recommendations");
report.recommendations.forEach((recommendation) => {
  const card = document.createElement("article");
  card.className = "recommendation";
  card.append(
    text("span", `${recommendation.priority} priority`, `priority ${recommendation.priority}`),
    text("h3", recommendation.title),
    text("p", recommendation.finding, "finding"),
  );
  const action = text("p", "", "action-copy");
  action.append(text("strong", "Testable action: "), document.createTextNode(recommendation.action));
  card.append(action);
  const evidenceList = document.createElement("ul");
  evidenceList.className = "evidence-list";
  evidenceList.append(text("li", `rule: ${recommendation.rule_id}`));
  recommendation.evidence.forEach((item) => {
    evidenceList.append(text("li", `${item.source} = ${item.value} · ${item.comparison}`));
  });
  card.append(evidenceList);
  recommendationGrid.append(card);
});

const disclaimers = document.getElementById("disclaimers");
report.disclaimers.forEach((disclaimer) => disclaimers.append(text("li", disclaimer)));

document.documentElement.dataset.ready = "true";
