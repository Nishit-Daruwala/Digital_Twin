"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Table2 } from "lucide-react";
import type { SeriesPoint } from "@/lib/types";
import { formatMinutes } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { VIZ, shortDate } from "./viz";

const AXIS = { fontSize: 11, fill: VIZ.axis, fontFamily: "var(--font-mono)" };

function ChartCard({
  title,
  subtitle,
  legend,
  table,
  children,
}: {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  table: React.ReactNode;
  children: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card className="flex animate-fade-up flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          aria-pressed={asTable}
          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Table2 className="h-3.5 w-3.5" aria-hidden /> {asTable ? "Chart" : "Table"}
        </button>
      </div>
      {legend && !asTable && (
        <ul className="flex gap-4 text-xs text-muted-foreground" aria-label="Legend">
          {legend.map((l) => (
            <li key={l.label} className="flex items-center gap-1.5">
              <span className="h-[3px] w-4 rounded-full" style={{ background: l.color }} aria-hidden />
              {l.label}
            </li>
          ))}
        </ul>
      )}
      {asTable ? <div className="max-h-64 overflow-auto">{table}</div> : children}
    </Card>
  );
}

function TipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2 text-xs shadow-lift">
      <p className="mb-1 font-semibold">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-1.5">
          {r.color && <span className="h-2 w-2 rounded-full" style={{ background: r.color }} aria-hidden />}
          <span className="text-muted-foreground">{r.label}</span>
          <span className="ml-auto pl-3 font-mono font-medium">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="sticky top-0 bg-card">
        <tr>{head.map((h) => <th key={h} className="border-b py-1.5 pr-3 font-semibold">{h}</th>)}</tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-border/60">
            {r.map((c, j) => <td key={j} className="py-1 pr-3">{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TrendChart({ data }: { data: SeriesPoint[] }) {
  const rows = data.map((d) => ({ ...d, label: shortDate(d.date) }));
  return (
    <ChartCard
      title="Mood & energy"
      subtitle={`Last ${data.length} check-ins, 1–5`}
      legend={[{ label: "Mood", color: VIZ.mood }, { label: "Energy", color: VIZ.energy }]}
      table={<SimpleTable head={["Day", "Mood", "Energy"]}
                          rows={data.map((d) => [shortDate(d.date), d.mood ?? "–", d.energy ?? "–"])} />}
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
            <CartesianGrid stroke={VIZ.grid} vertical={false} />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: VIZ.baseline }}
                   interval="preserveStartEnd" minTickGap={24} />
            <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} tick={AXIS} tickLine={false} axisLine={false} />
            <Tooltip
              cursor={{ stroke: VIZ.baseline, strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TipBox title={String(label)} rows={payload.map((p) => ({
                    label: String(p.name), value: String(p.value ?? "–"), color: String(p.color),
                  }))} />
                ) : null}
            />
            {(["mood", "energy"] as const).map((k) => (
              <Line key={k} type="monotone" dataKey={k} name={k === "mood" ? "Mood" : "Energy"}
                    stroke={VIZ[k]} strokeWidth={2} dot={false} connectNulls
                    activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }}
                    animationDuration={700} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

export function SleepChart({ data }: { data: SeriesPoint[] }) {
  const rows = data.map((d) => ({ ...d, label: shortDate(d.date) }));
  return (
    <ChartCard
      title="Sleep"
      subtitle="Hours, as logged in check-ins"
      table={<SimpleTable head={["Day", "Hours"]}
                          rows={data.map((d) => [shortDate(d.date), d.sleep_hours ?? "–"])} />}
    >
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
            <CartesianGrid stroke={VIZ.grid} vertical={false} />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: VIZ.baseline }}
                   interval="preserveStartEnd" minTickGap={24} />
            <YAxis domain={[3, 10]} ticks={[4, 6, 8, 10]} tick={AXIS} tickLine={false} axisLine={false} />
            <Tooltip
              cursor={{ stroke: VIZ.baseline, strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TipBox title={String(label)} rows={[{ label: "Sleep", value: `${payload[0].value ?? "–"} h` }]} />
                ) : null}
            />
            <Line type="monotone" dataKey="sleep_hours" name="Sleep" stroke={VIZ.sleep} strokeWidth={2}
                  dot={false} connectNulls activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }}
                  animationDuration={700} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

export function CategoryChart({ data }: { data: { category: string; minutes: number }[] }) {
  const rows = data.slice(0, 8);
  return (
    <ChartCard
      title="Where your time went"
      subtitle="Completed activities, last 14 days"
      table={<SimpleTable head={["Category", "Time"]}
                          rows={rows.map((r) => [r.category, formatMinutes(r.minutes)])} />}
    >
      <div style={{ height: Math.max(120, rows.length * 34) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }}
                    barCategoryGap={8}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="category" width={96} tickLine={false} axisLine={false}
                   tick={{ fontSize: 12, fill: "hsl(222 45% 16%)" }} />
            <Tooltip
              cursor={{ fill: "rgba(11,11,11,0.04)" }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <TipBox title={String(payload[0].payload.category)}
                          rows={[{ label: "Time", value: formatMinutes(Number(payload[0].value)) }]} />
                ) : null}
            />
            <Bar dataKey="minutes" fill={VIZ.minutes} radius={[0, 4, 4, 0]} maxBarSize={20}
                 animationDuration={700}>
              {/* Own <text> so short bars never wrap the label ("2h 15m" stays on one line) */}
              <LabelList dataKey="minutes"
                         content={(props) => {
                           const { x, y, width, height, value } = props;
                           return (
                             <text x={Number(x) + Number(width) + 6} y={Number(y) + Number(height) / 2}
                                   dominantBaseline="central" fontSize={11} fill={VIZ.axis}
                                   fontFamily="var(--font-mono)">
                               {formatMinutes(Number(value))}
                             </text>
                           );
                         }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
