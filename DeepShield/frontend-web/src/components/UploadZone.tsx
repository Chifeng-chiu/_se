import { useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";

interface Props {
  onFile: (f: File) => void;
  loading: boolean;
}

export default function UploadZone({ onFile, loading }: Props) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onClick={() => !loading && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !loading) onFile(f);
      }}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition ${
        drag
          ? "border-sky-400 bg-sky-500/10"
          : "border-line bg-panel hover:border-slate-500"
      } ${loading ? "pointer-events-none opacity-60" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*,audio/*,.mp4,.mov,.webm,.mkv,.avi,.mp3,.wav,.m4a,.flac,.ogg,.opus"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-sky-500/15 text-sky-300">
        {loading ? <Loader2 className="animate-spin" size={26} /> : <FileUp size={26} />}
      </div>
      <p className="text-lg font-semibold text-slate-200">
        {loading ? "鑑識中，請稍候…" : "拖曳可疑影音到這裡，或點擊選擇檔案"}
      </p>
      <p className="mt-1 text-sm text-slate-500">
        支援 mp4 / mov / webm / mp3 / wav / m4a（上限 200MB）→ 直連後端深度鑑識
      </p>
    </div>
  );
}
