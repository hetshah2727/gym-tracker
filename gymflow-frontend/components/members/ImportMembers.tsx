"use client";

import { CheckCircle2, Download, FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Button, ErrorNote } from "@/components/shared/ui";
import { cn } from "@/lib/utils";
import { api } from "@/services/api";

interface Row { row: number; name: string; phone: string | null; plan: string | null; end_date: string | null; issue: string | null; note: string | null }
interface Result { preview: boolean; created: number; with_membership: number; skipped: number; rows: Row[] }

const TEMPLATE = "Name,Phone,Email,Gender,Plan,Joining date,Expiry date,Paid\n"
  + "Amit Shah,9824012345,amit@example.com,Male,Monthly,01/11/2026,30/11/2026,Yes\n"
  + "Priya Kapoor,9824098765,,Female,Quarterly,15/09/2026,13/12/2026,No\n";

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "gymflow-members-template.csv" });
  a.click();
  URL.revokeObjectURL(url);
}

/** Upload the old register (Excel/CSV) -> check the preview -> import. Re-running never duplicates anyone. */
export function ImportMembers({ onDone }: { onDone?: (created: number) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async (f: File, preview: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await api<Result>("/members/import", { method: "POST", body: fd, query: { preview } });
      setResult(r);
      if (!preview) onDone?.(r.created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  if (result && !result.preview) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <CheckCircle2 className="h-10 w-10 text-money" />
        <p className="font-display text-lg font-bold">{result.created} members added</p>
        <p className="text-sm text-muted">{result.with_membership} with their current membership{result.skipped ? ` · ${result.skipped} rows skipped` : ""}.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ErrorNote message={error} />
      <button type="button" onClick={() => input.current?.click()}
        className="flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-border p-8 text-center transition hover:border-brand/50 hover:bg-surface-2">
        <FileSpreadsheet className="h-8 w-8 text-brand" />
        <span className="font-semibold">{file ? file.name : "Choose your Excel or CSV file"}</span>
        <span className="text-xs text-muted">Needs at least a Name and a Phone column. Plan and expiry date are optional.</span>
      </button>
      <input ref={input} type="file" accept=".xlsx,.csv" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setResult(null); void send(f, true); } }} />
      <button type="button" onClick={downloadTemplate} className="inline-flex items-center gap-1.5 text-xs text-muted underline">
        <Download className="h-3.5 w-3.5" /> Download a sample file
      </button>

      {result?.preview && (
        <div className="space-y-3">
          <p className="text-sm">
            <strong>{result.created}</strong> members ready to add{result.with_membership ? <>, <strong>{result.with_membership}</strong> with a membership</> : null}
            {result.skipped ? <> · <span className="text-warning">{result.skipped} rows will be skipped</span></> : null}
          </p>
          <div className="max-h-64 overflow-y-auto rounded-xl border border-border">
            <table className="table-base">
              <thead><tr><th>Row</th><th>Name</th><th>Phone</th><th>Plan / ends</th><th /></tr></thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row} className={cn(r.issue && "text-muted")}>
                    <td className="text-xs">{r.row}</td><td>{r.name || "—"}</td><td className="text-xs">{r.phone ?? "—"}</td>
                    <td className="text-xs">{r.plan ? `${r.plan}${r.end_date ? ` · ${r.end_date}` : ""}` : "—"}</td>
                    <td className="text-xs">{r.issue ? <span className="text-warning">{r.issue}</span> : r.note ? <span className="text-muted">{r.note}</span> : <span className="text-money">OK</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button disabled={!result.created || !file} loading={busy} onClick={() => file && send(file, false)}>
            <Upload className="h-4 w-4" /> Add {result.created} members
          </Button>
        </div>
      )}
      {busy && !result && <p className="text-sm text-muted">Reading your file…</p>}
    </div>
  );
}
