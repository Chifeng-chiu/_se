import { useState } from "react";
import { FileText, Share2 } from "lucide-react";
import type { DeepReport } from "../types";
import { shortHash } from "./evidenceUtils";
import AlertCardModal from "./AlertCardModal";
import ForensicPrintView from "./ForensicPrintView";

export default function EvidenceToolbar({
  report,
  sourceLabel,
}: {
  report: DeepReport;
  sourceLabel: string;
}) {
  const [showCard, setShowCard] = useState(false);
  const [showPrint, setShowPrint] = useState(false);
  const caseId = `DS-${(report.sha256_hash ?? "demo").slice(0, 8).toUpperCase()}-${new Date(
    report.analyzed_at ?? Date.now()
  )
    .toISOString()
    .slice(0, 10)
    .replace(/-/g, "")}`;

  return (
    <>
      <div className="no-print flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-rose-500/10 px-3 py-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-extrabold text-amber-200">
          <Share2 size={16} />
          證據輸出與防詐分享
        </span>
        <span className="hidden font-mono text-[11px] text-slate-500 lg:inline" title={report.sha256_hash ?? ""}>
          SHA-256: {shortHash(report.sha256_hash)}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          <button
            onClick={() => setShowCard(true)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-rose-500 to-orange-500 px-4 py-2 text-sm font-bold text-white transition hover:brightness-110"
          >
            📲 LINE 防詐圖卡
          </button>
          <button
            onClick={() => setShowPrint(true)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-900 transition hover:bg-white"
          >
            <FileText size={16} /> 匯出 PDF 鑑識報告
          </button>
        </div>
      </div>
      {showCard && (
        <div className="no-print">
          <AlertCardModal report={report} sourceLabel={sourceLabel} onClose={() => setShowCard(false)} />
        </div>
      )}
      {showPrint && (
        <ForensicPrintView
          report={report}
          sourceLabel={sourceLabel}
          caseId={caseId}
          onClose={() => setShowPrint(false)}
        />
      )}
    </>
  );
}
