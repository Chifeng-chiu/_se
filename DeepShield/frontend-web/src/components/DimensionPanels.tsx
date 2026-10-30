import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import type { DeepReport } from "../types";

function barColor(v: number) {
  return v < 35 ? "bg-emerald-500" : v < 65 ? "bg-amber-500" : "bg-red-500";
}
function textColor(v: number) {
  return v < 35 ? "text-emerald-300" : v < 65 ? "text-amber-300" : "text-red-300";
}

export default function DimensionPanels({ report }: { report: DeepReport }) {
  const d = report.dimensions;
  const skipped = new Set(report.skipped_dimensions ?? []);
  const rows = [
    { key: "audio", name: "語音鑑識", value: d.audio?.risk ?? 0, skipped: skipped.has("audio") },
    { key: "visual", name: "視覺深偽", value: d.visual?.risk ?? 0, skipped: skipped.has("visual") },
    { key: "av_sync", name: "唇音同步", value: d.av_sync?.risk ?? 0, skipped: skipped.has("avsync") },
    { key: "semantic", name: "詐騙語意", value: d.semantic?.risk ?? 0, skipped: skipped.has("semantic") },
  ];
  const radarData = rows.map((r) => ({ dim: r.name, risk: r.skipped ? 0 : Math.round(r.value) }));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-line bg-panel p-4">
        <h3 className="mb-1 text-sm font-semibold text-slate-300">四維度風險雷達</h3>
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} outerRadius="72%">
              <PolarGrid stroke="#24365a" />
              <PolarAngleAxis dataKey="dim" tick={{ fill: "#9fb3c8", fontSize: 12 }} />
              <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
              <Radar dataKey="risk" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.45} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="flex flex-col justify-center gap-3 rounded-xl border border-line bg-panel p-4">
        {rows.map((r) => (
          <div key={r.key}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="text-slate-300">
                {r.name}
                {r.skipped && (
                  <span className="ml-2 rounded bg-slate-700/60 px-1.5 py-0.5 text-[11px] text-slate-400">
                    略過
                  </span>
                )}
              </span>
              <span className={`font-mono font-bold ${textColor(r.value)}`}>
                {r.skipped ? "—" : r.value.toFixed(1)}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all ${barColor(r.value)}`}
                style={{ width: `${r.skipped ? 0 : Math.min(100, r.value)}%` }}
              />
            </div>
          </div>
        ))}
        <p className="mt-1 text-xs text-slate-500">
          融合權重：語音 30% / 視覺 30% / 唇同步 15% / 語意 25%（略過維度自動重分配）
        </p>
      </div>
    </div>
  );
}
