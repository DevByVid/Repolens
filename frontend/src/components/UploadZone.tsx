"use client";
import { useCallback, useState } from "react";
import { Upload, Archive, Loader2 } from "lucide-react";

interface Props {
  onUpload: (file: File) => void;
  loading: boolean;
}

export default function UploadZone({ onUpload, loading }: Props) {
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    (f: File) => {
      if (!f.name.endsWith(".zip")) {
        alert("Please upload a .zip archive of your repository.");
        return;
      }
      onUpload(f);
    },
    [onUpload]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  return (
    <label
      className={`upload-zone ${dragOver ? "drag-over" : ""} ${loading ? "loading" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <input
        type="file"
        accept=".zip"
        style={{ display: "none" }}
        disabled={loading}
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
      />
      <div className="upload-icon">
        {loading ? (
          <Loader2 size={40} className="spin" />
        ) : dragOver ? (
          <Archive size={40} />
        ) : (
          <Upload size={40} />
        )}
      </div>
      <p className="upload-headline">
        {loading ? "Uploading & caching repository…" : "Drop your repo .zip here"}
      </p>
      <p className="upload-sub">
        {loading
          ? "Creating a 30-minute Gemini context cache"
          : "or click to browse · .zip archives only"}
      </p>
    </label>
  );
}
