import clsx from "clsx";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";

export function FilePicker({ accept, label, file, onFile }: {
  accept: string;
  label: string;
  file: File | null;
  onFile: (f: File | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => ref.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && ref.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFile(e.dataTransfer.files[0] ?? null);
      }}
      className={clsx(
        "flex cursor-pointer items-center gap-3 rounded-md border border-dashed px-4 py-4 text-sm",
        over ? "border-brand bg-brand-tint" : "border-line bg-white hover:border-brand/60",
      )}
    >
      <Upload className="h-4 w-4 text-ink-soft" />
      <span className={file ? "font-medium" : "text-ink-soft"}>{file ? file.name : label}</span>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}
