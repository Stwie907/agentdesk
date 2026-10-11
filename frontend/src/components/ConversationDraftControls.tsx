import { useState } from "react";

type Props = {
  agentId: number;
  enabled: boolean;
  error: string | null;
  disabled: boolean;
  onToggle: (enabled: boolean) => void;
  onClear: () => boolean;
};

export function ConversationDraftControls({ agentId, enabled, error, disabled, onToggle, onClear }: Props) {
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  return (
    <section aria-label="Conversation draft saving">
      <label>
        <input type="checkbox" checked={enabled} disabled={disabled || confirm}
          onChange={(event) => { onToggle(event.target.checked); setNotice(null); }} />
        Keep this Agent's drafts on this browser
      </label>
      <p>{enabled ? "Browser draft saving is on." : "Browser draft saving is off."}
        {" "}When on, re-select this Agent and conversation after a reload to restore unsent chat and title drafts.</p>
      <p>Turning saving off keeps existing browser copies. Use the clear button to remove them.</p>
      <button type="button" disabled={disabled || confirm} onClick={() => { setConfirm(true); setNotice(null); }}>
        Clear saved drafts for this Agent
      </button>
      {confirm && <div role="group" aria-label="Confirm clearing saved drafts">
        <p>Clear browser copies for Agent {agentId} and turn saving off? Drafts already in this page will be kept.</p>
        <button type="button" disabled={disabled} onClick={() => {
          const cleared = onClear(); setConfirm(false);
          setNotice(cleared ? "Saved browser drafts cleared for this Agent. Saving is off; current page drafts were kept." :
            "Saved drafts could not be fully cleared. Saving is off in this page; current page drafts were kept.");
        }}>Confirm clear saved drafts</button>
        <button type="button" disabled={disabled} onClick={() => setConfirm(false)}>Cancel clearing saved drafts</button>
      </div>}
      {error !== null && <p role="alert">{error}</p>}
      {notice !== null && <p role="status">{notice}</p>}
    </section>
  );
}
