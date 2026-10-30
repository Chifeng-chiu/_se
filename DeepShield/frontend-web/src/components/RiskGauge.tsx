/** 綜合風險儀表板: 半圓弧 SVG Gauge (0-100 偽造機率). */
export default function RiskGauge({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  const W = 260;
  const H = 150;
  const cx = W / 2;
  const cy = 128;
  const r = 100;
  const arc = (a0: number, a1: number) => {
    const p = (a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x0, y0] = p(a0);
    const [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  const color = v < 35 ? "#10b981" : v < 65 ? "#f59e0b" : "#ef4444";
  const frac = v / 100;
  const endA = Math.PI + Math.PI * frac;
  // 刻度
  const ticks = [0, 25, 50, 75, 100].map((t) => {
    const a = Math.PI + (Math.PI * t) / 100;
    const x0 = cx + (r - 8) * Math.cos(a);
    const y0 = cy + (r - 8) * Math.sin(a);
    const x1 = cx + (r + 2) * Math.cos(a);
    const y1 = cy + (r + 2) * Math.sin(a);
    return { x0, y0, x1, y1, t };
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[320px]">
      <path d={arc(Math.PI, 2 * Math.PI)} stroke="#1e2d47" strokeWidth={16} fill="none" strokeLinecap="round" />
      {v > 0.5 && (
        <path d={arc(Math.PI, endA)} stroke={color} strokeWidth={16} fill="none" strokeLinecap="round" />
      )}
      {ticks.map((k) => (
        <g key={k.t}>
          <line x1={k.x0} y1={k.y0} x2={k.x1} y2={k.y1} stroke="#475569" strokeWidth={2} />
        </g>
      ))}
      <text x={cx} y={cy - 18} textAnchor="middle" fill="#f1f5f9" fontSize={44} fontWeight={800}>
        {v.toFixed(1)}
      </text>
      <text x={cx} y={cy + 4} textAnchor="middle" fill="#94a3b8" fontSize={12}>
        偽造機率 / 100
      </text>
    </svg>
  );
}
