import { useEffect, useRef, useState } from "react";
import { ClipboardCopy, Download, X } from "lucide-react";
import type { DeepReport } from "../types";
import { loadEvidenceThumbs, shortHash, STATUS_THEME, topEvidence } from "./evidenceUtils";

const W = 1080;
const H = 1350;

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const ch of text) {
    const test = line + ch;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = ch;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

async function drawAlertCard(
  canvas: HTMLCanvasElement,
  report: DeepReport,
  sourceLabel: string
): Promise<void> {
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const theme = STATUS_THEME[report.status] ?? STATUS_THEME.WARNING;

  // 背景
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, "#0B1220");
  bg.addColorStop(1, "#16233F");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // 頂部警報條
  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, W, 240);
  ctx.fillStyle = theme.fg;
  ctx.textAlign = "center";
  ctx.font = "900 64px 'Noto Sans TC','Microsoft JhengHei',sans-serif";
  ctx.fillText("DeepShield 防詐警報", W / 2, 90);
  ctx.font = "700 40px 'Noto Sans TC','Microsoft JhengHei',sans-serif";
  const subtitle =
    report.status === "DANGER"
      ? "高度疑似 AI 偽造內容！請勿受騙匯款！"
      : report.status === "WARNING"
        ? "內容可疑！匯款前請先查證！"
        : "暫無明顯偽造特徵，仍請保持警覺";
  const subLines = wrapText(ctx, `警告：${subtitle}`, W - 120);
  subLines.forEach((ln, i) => ctx.fillText(ln, W / 2, 155 + i * 52));

  // 核心數據大字報
  ctx.textAlign = "center";
  ctx.fillStyle = "#FFFFFF";
  ctx.font = "900 120px 'Noto Sans TC',sans-serif";
  ctx.fillText(`偽造風險 ${report.fake_probability.toFixed(1)}%`, W / 2, 400);
  ctx.font = "900 56px 'Noto Sans TC',sans-serif";
  ctx.fillStyle = theme.bar;
  ctx.fillText(`(${report.status})  信任分數 ${report.trust_score.toFixed(1)} / 100`, W / 2, 470);

  // 四維度分數條
  const dims: Array<{ name: string; v: number }> = [
    { name: "語音鑑識", v: report.dimensions.audio.risk },
    { name: "視覺深偽", v: report.dimensions.visual.risk },
    { name: "唇音同步", v: report.dimensions.av_sync.risk },
    { name: "防詐語意", v: report.dimensions.semantic.risk },
  ];
  ctx.textAlign = "left";
  let y = 540;
  for (const d of dims) {
    ctx.font = "700 34px 'Noto Sans TC',sans-serif";
    ctx.fillStyle = "#CBD5E1";
    ctx.fillText(`${d.name}  ${d.v.toFixed(0)}%`, 80, y);
    // 條底
    ctx.fillStyle = "#26334F";
    ctx.fillRect(80, y + 14, W - 160, 26);
    // 條 fill
    const col = d.v >= 60 ? "#EF4444" : d.v >= 40 ? "#F59E0B" : "#10B981";
    ctx.fillStyle = col;
    ctx.fillRect(80, y + 14, ((W - 160) * Math.min(100, Math.max(0, d.v))) / 100, 26);
    y += 86;
  }

  // 破綻鐵證摘要
  ctx.fillStyle = "#FDE68A";
  ctx.font = "900 40px 'Noto Sans TC',sans-serif";
  ctx.fillText("破綻鐵證", 80, y + 20);
  const evs = topEvidence(report, 3);
  ctx.font = "600 33px 'Noto Sans TC',sans-serif";
  ctx.fillStyle = "#FFFFFF";
  let ey = y + 66;
  evs.forEach((e, i) => {
    const lines = wrapText(ctx, `❗ ${i + 1}. ${e}`, W - 160);
    lines.forEach((ln) => {
      ctx.fillText(ln, 80, ey);
      ey += 44;
    });
    ey += 6;
  });

  // 視覺鐵證縮圖 (右下並排)
  const { heat, spec } = await loadEvidenceThumbs(report);
  const thumbY = 1060;
  const thumbW = (W - 80 * 2 - 24) / 2;
  const thumbH = 170;
  ctx.font = "700 28px 'Noto Sans TC',sans-serif";
  ctx.fillStyle = "#93C5FD";
  ctx.fillText("視覺熱力圖", 80, thumbY - 12);
  ctx.fillText("聲紋頻譜圖", 80 + thumbW + 24, thumbY - 12);
  const drawThumb = (img: HTMLImageElement | null, x: number) => {
    ctx.fillStyle = "#020617";
    ctx.fillRect(x, thumbY, thumbW, thumbH);
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 3;
    ctx.strokeRect(x, thumbY, thumbW, thumbH);
    if (img) {
      // contain fit
      const s = Math.min(thumbW / img.width, thumbH / img.height);
      const dw = img.width * s;
      const dh = img.height * s;
      ctx.drawImage(img, x + (thumbW - dw) / 2, thumbY + (thumbH - dh) / 2, dw, dh);
    } else {
      ctx.fillStyle = "#64748B";
      ctx.font = "500 26px 'Noto Sans TC',sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("無圖", x + thumbW / 2, thumbY + thumbH / 2);
      ctx.textAlign = "left";
    }
  };
  drawThumb(heat, 80);
  drawThumb(spec, 80 + thumbW + 24);

  // 來源 + 底部浮水印
  ctx.fillStyle = "#94A3B8";
  ctx.font = "500 26px 'Noto Sans TC',sans-serif";
  const srcLines = wrapText(ctx, `來源：${sourceLabel}`, W - 160);
  srcLines.slice(0, 1).forEach((ln) => ctx.fillText(ln, 80, thumbY + thumbH + 36));
  ctx.fillStyle = "#E2E8F0";
  ctx.font = "600 24px 'Noto Sans TC',sans-serif";
  ctx.fillText("由 DeepShield AI 雙層防禦系統鑑識", 80, H - 52);
  ctx.fillStyle = "#64748B";
  ctx.font = "500 22px monospace";
  ctx.fillText(`SHA-256: ${shortHash(report.sha256_hash)}`, 80, H - 22);
}

export default function AlertCardModal({
  report,
  sourceLabel,
  onClose,
}: {
  report: DeepReport;
  sourceLabel: string;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setMsg("圖卡繪製中…");
    const canvas = canvasRef.current;
    if (!canvas) return;
    void drawAlertCard(canvas, report, sourceLabel).then(() => {
      if (!cancelled) {
        setReady(true);
        setMsg(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [report, sourceLabel]);

  function download() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) {
        setMsg("匯出失敗，請重試");
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `deepshield-alert-${report.status}-${report.fake_probability.toFixed(1)}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setMsg("已下載 PNG，可直接傳進 LINE 群組");
    }, "image/png");
  }

  async function copyImage() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/png"));
      if (!blob) {
        setMsg("複製失敗：無法產生圖片");
        return;
      }
      const ClipboardItemCtor =
        (window as unknown as { ClipboardItem?: typeof ClipboardItem }).ClipboardItem;
      if (!ClipboardItemCtor || !navigator.clipboard?.write) {
        setMsg("此瀏覽器不支援複製圖片，請改用下載 PNG");
        return;
      }
      await navigator.clipboard.write([new ClipboardItemCtor({ "image/png": blob })]);
      setMsg("已複製！可直接 Ctrl+V 貼進 LINE / Discord");
    } catch {
      setMsg("複製被拒絕，請改用下載 PNG（需 HTTPS / localhost 才可複製）");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-3xl rounded-2xl border border-line bg-panel p-4">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="font-extrabold text-slate-100">LINE 防詐警告圖卡預覽（1080×1350）</h3>
          <button
            onClick={onClose}
            className="ml-auto rounded-lg border border-line p-1.5 text-slate-400 hover:text-white"
            aria-label="關閉"
          >
            <X size={16} />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-auto rounded-xl bg-black/40 p-2 text-center">
          <canvas ref={canvasRef} style={{ width: "100%", height: "auto" }} />
        </div>
        {msg && <p className="mt-2 text-center text-sm text-amber-200">{msg}</p>}
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          <button
            onClick={download}
            disabled={!ready}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-rose-500 to-orange-500 px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40"
          >
            <Download size={16} /> 下載 PNG 圖卡
          </button>
          <button
            onClick={() => void copyImage()}
            disabled={!ready}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40"
          >
            <ClipboardCopy size={16} /> 一鍵複製圖片
          </button>
        </div>
      </div>
    </div>
  );
}
