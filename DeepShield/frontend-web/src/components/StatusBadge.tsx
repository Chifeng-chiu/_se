import { ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import type { Verdict } from "../types";

const MAP: Record<Verdict, { text: string; cls: string; Icon: typeof ShieldCheck }> = {
  SAFE: { text: "SAFE 安全", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", Icon: ShieldCheck },
  WARNING: { text: "WARNING 可疑", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40", Icon: TriangleAlert },
  DANGER: { text: "DANGER 高風險", cls: "bg-red-500/15 text-red-300 border-red-500/40", Icon: ShieldAlert },
};

export default function StatusBadge({ status, big = false }: { status: Verdict; big?: boolean }) {
  const { text, cls, Icon } = MAP[status] ?? MAP.WARNING;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-semibold ${cls} ${
        big ? "text-lg px-4 py-1.5" : "text-sm"
      } ${status === "DANGER" ? "danger-glow" : ""}`}
    >
      <Icon size={big ? 20 : 16} />
      {text}
    </span>
  );
}
