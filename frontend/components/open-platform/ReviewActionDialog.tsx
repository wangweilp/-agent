"use client";
import { useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";

type ActionType = "approve" | "reject" | "request_changes";

const ACTION_LABELS: Record<ActionType, { title: string; color: string; requiresNotes: boolean; notesLabel: string }> = {
  approve: { title: "Approve Submission", color: "text-emerald-300", requiresNotes: false, notesLabel: "Notes (optional)" },
  reject: { title: "Reject Submission", color: "text-red-300", requiresNotes: true, notesLabel: "Reason (required)" },
  request_changes: { title: "Request Changes", color: "text-amber-300", requiresNotes: true, notesLabel: "Changes needed (required)" },
};

interface Props {
  open: boolean;
  action: ActionType;
  submissionId: string;
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (notes: string, checklist: Record<string, unknown>) => void;
}

export function ReviewActionDialog({ open, action, submissionId, saving, error, onClose, onSubmit }: Props) {
  const [notes, setNotes] = useState("");
  const [checklistText, setChecklistText] = useState("{}");
  const [jsonErr, setJsonErr] = useState<string | null>(null);

  if (!open) return null;
  const cfg = ACTION_LABELS[action];

  function handleSubmit() {
    setJsonErr(null);
    let checklist: Record<string, unknown> = {};
    if (checklistText.trim()) {
      try { checklist = JSON.parse(checklistText); } catch { setJsonErr("Checklist JSON 格式错误"); return; }
    }
    if (cfg.requiresNotes && !notes.trim()) { setJsonErr("备注不能为空"); return; }
    onSubmit(notes, checklist);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-lg border border-os-border bg-os-base shadow-2xl">
        <div className="flex items-center justify-between border-b border-os-border px-5 py-3">
          <h2 className={`text-sm font-semibold ${cfg.color}`}>{cfg.title}</h2>
          <button onClick={onClose} disabled={saving} className="rounded p-1 text-os-subtle hover:text-os-text-high disabled:opacity-50"><X size={16}/></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <p className="font-mono text-2xs text-os-muted">{submissionId}</p>
          <div>
            <label className="mb-1 block text-xs font-medium text-os-subtle">{cfg.notesLabel}</label>
            <textarea rows={3} value={notes} onChange={e => setNotes(e.target.value)}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
              placeholder={cfg.requiresNotes ? "输入原因/建议..." : "可选备注"} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-os-subtle">Checklist (JSON)</label>
            <textarea rows={4} value={checklistText} onChange={e => setChecklistText(e.target.value)} spellCheck={false}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent" />
          </div>
          {jsonErr && <div className="flex items-center gap-2 rounded border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-300"><AlertTriangle size={13}/>{jsonErr}</div>}
          {error && <div className="flex items-center gap-2 rounded border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-200"><AlertTriangle size={13}/>{error}</div>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-os-border px-5 py-3">
          <button onClick={onClose} disabled={saving} className="inline-flex h-8 items-center rounded border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-50">Cancel</button>
          <button onClick={handleSubmit} disabled={saving}
            className="inline-flex h-8 items-center gap-2 rounded bg-os-accent px-4 text-xs font-medium text-white hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed">
            {saving ? <Loader2 size={12} className="animate-spin"/> : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
