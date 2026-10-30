import { Printer, X } from "lucide-react";
import { imgSrc } from "../api";
import type { DeepReport } from "../types";
import { analyzedAtText } from "./evidenceUtils";

function fmtT(t: number) {
  return `${t.toFixed(1)}s`;
}

export default function ForensicPrintView({
  report,
  sourceLabel,
  caseId,
  onClose,
}: {
  report: DeepReport;
  sourceLabel: string;
  caseId: string;
  onClose: () => void;
}) {
  const spec = imgSrc(report.dimensions.audio.spectrogram_b64, "png");
  const heat = imgSrc(report.dimensions.visual.heatmap_b64, "jpg");
  const dims: Array<{ k: string; name: string; v: number; note?: string }> = [
    { k: "audio", name: "語音鑑識 (30%)", v: report.dimensions.audio.risk, note: report.dimensions.audio.note },
    { k: "visual", name: "視覺深偽 (30%)", v: report.dimensions.visual.risk, note: report.dimensions.visual.note },
    { k: "av_sync", name: "唇音同步 (15%)", v: report.dimensions.av_sync.risk, note: report.dimensions.av_sync.note },
    { k: "semantic", name: "防詐語意 (25%)", v: report.dimensions.semantic.risk, note: undefined },
  ];
  const weights = report.fusion?.weights_used;
  const boosts = report.fusion?.boosts ?? [];
  const transcript = report.dimensions.semantic.transcript ?? [];
  const fullText = report.dimensions.semantic.full_text ?? "";
  const hits = report.dimensions.semantic.hits ?? [];

  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-black/70 p-4">
      <div className="no-print mx-auto mb-3 flex max-w-4xl items-center gap-2">
        <h3 className="font-extrabold text-white">正式鑑識報告預覽（A4 白底，列印即存成 PDF）</h3>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => window.print()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2 text-sm font-bold text-black hover:bg-white"
          >
            <Printer size={16} /> 列印 / 存成 PDF
          </button>
          <button
            onClick={onClose}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-500 px-4 py-2 text-sm text-slate-200"
          >
            <X size={16} /> 關閉
          </button>
        </div>
      </div>

      <div
        id="print-report"
        className="print-sheet mx-auto max-w-4xl rounded-lg bg-white p-8 text-black"
      >
        {/* 頁首 */}
        <div style={{ borderBottom: "3px solid #000", paddingBottom: 12 }}>
          <h1 style={{ fontSize: 24, fontWeight: 900 }}>DeepShield 數位鑑識報告</h1>
          <p style={{ fontSize: 13, color: "#334155" }}>Forensic Evidence Report · AI 語音與深偽影片雙層防禦系統</p>
        </div>

        {/* 案件資訊 */}
        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 16 }}>一、案件資訊</h2>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
          <tbody>
            {[
              ["案件編號", caseId],
              ["鑑識時間", analyzedAtText(report)],
              ["來源", sourceLabel],
              ["檔案名稱", report.filename ?? sourceLabel],
              ["SHA-256 指紋", report.sha256_hash ?? "未提供 (示範案例)"],
              ["片長", `${report.duration.toFixed(1)} 秒`],
              ["總體偽造機率", `${report.fake_probability.toFixed(1)}% (${report.status})`],
              ["信任分數", `${report.trust_score.toFixed(1)} / 100`],
            ].map(([k, v]) => (
              <tr key={k}>
                <td style={{ border: "1px solid #999", padding: "6px 8px", fontWeight: 700, width: 130, background: "#F1F5F9" }}>{k}</td>
                <td style={{ border: "1px solid #999", padding: "6px 8px", wordBreak: "break-all", fontFamily: k.includes("SHA") ? "monospace" : undefined }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* 四維度 */}
        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 18 }}>二、四維度風險評分</h2>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
          <thead>
            <tr>
              {["維度", "風險分數", "備註"].map((h) => (
                <th key={h} style={{ border: "1px solid #999", padding: "6px 8px", background: "#0F172A", color: "#fff" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dims.map((d) => (
              <tr key={d.k}>
                <td style={{ border: "1px solid #999", padding: "6px 8px", fontWeight: 700 }}>{d.name}</td>
                <td style={{ border: "1px solid #999", padding: "6px 8px" }}>{d.v.toFixed(1)}</td>
                <td style={{ border: "1px solid #999", padding: "6px 8px", color: "#334155" }}>{d.note ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 18 }}>三、融合權重與觸發原因</h2>
        <p style={{ fontSize: 13, marginTop: 6 }}>
          實際使用權重：
          {weights
            ? Object.entries(weights).map(([k, v]) => ` ${k}=${(Number(v) * 100).toFixed(1)}%`).join(" ·")
            : "（舊報告無 fusion 紀錄，採預設 30/30/15/25）"}
        </p>
        {boosts.length > 0 ? (
          <ul style={{ fontSize: 13, marginTop: 6, paddingLeft: 18 }}>
            {boosts.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        ) : (
          <p style={{ fontSize: 13, marginTop: 6, color: "#475569" }}>無保底加權觸發（各維度直接加權平均）。</p>
        )}

        {/* 時間軸 */}
        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 18 }}>
          四、異常時間軸事件（共 {report.timeline.length} 筆）
        </h2>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", marginTop: 8 }}>
          <thead>
            <tr>
              {["#", "起訖", "類型", "描述"].map((h) => (
                <th key={h} style={{ border: "1px solid #999", padding: "5px 6px", background: "#0F172A", color: "#fff" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.timeline.map((ev, i) => (
              <tr key={i}>
                <td style={{ border: "1px solid #999", padding: "5px 6px" }}>{i + 1}</td>
                <td style={{ border: "1px solid #999", padding: "5px 6px", whiteSpace: "nowrap" }}>{fmtT(ev.start)}–{fmtT(ev.end)}</td>
                <td style={{ border: "1px solid #999", padding: "5px 6px" }}>{ev.type}</td>
                <td style={{ border: "1px solid #999", padding: "5px 6px" }}>{ev.description}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* 圖證 */}
        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 18 }}>五、頻譜圖與熱力圖</h2>
        <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 12, fontWeight: 700 }}>音訊梅爾頻譜圖</p>
            {spec ? (
              <img src={spec} alt="spectrogram" style={{ width: "100%", border: "1px solid #999" }} />
            ) : (
              <p style={{ fontSize: 12, color: "#64748B" }}>無頻譜圖</p>
            )}
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 12, fontWeight: 700 }}>換臉邊界熱力圖</p>
            {heat ? (
              <img src={heat} alt="heatmap" style={{ width: "100%", border: "1px solid #999" }} />
            ) : (
              <p style={{ fontSize: 12, color: "#64748B" }}>無熱力圖（純音檔或未偵測人臉）</p>
            )}
          </div>
        </div>

        {/* 逐字稿 */}
        <h2 style={{ fontSize: 16, fontWeight: 800, marginTop: 18 }}>六、完整逐字稿（標記 {hits.length} 處詐騙詞彙）</h2>
        {transcript.length > 0 ? (
          <div style={{ fontSize: 12, marginTop: 8 }}>
            {transcript.map((s, i) => (
              <p key={i} style={{ margin: "4px 0" }}>
                [{s.start.toFixed(1)}s] {s.text}
              </p>
            ))}
            {fullText && <p style={{ marginTop: 8, color: "#334155" }}>全文：{fullText}</p>}
          </div>
        ) : (
          <p style={{ fontSize: 13, color: "#64748B" }}>無逐字稿（後端未啟用語音辨識）。</p>
        )}

        {/* 簽章 */}
        <div style={{ borderTop: "2px solid #000", marginTop: 24, paddingTop: 10, fontSize: 12, color: "#334155" }}>
          <p>DeepShield 自動化多模態鑑識引擎簽章 · 本報告由系統自動產生，僅供風險參考，不構成法律證據。</p>
          <p style={{ fontFamily: "monospace" }}>SHA-256: {report.sha256_hash ?? "N/A"} · {analyzedAtText(report)}</p>
        </div>
      </div>
    </div>
  );
}
