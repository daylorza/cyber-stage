import { useEffect, useRef } from "react";

export default function ConfirmDialog({ message, onConfirm, onCancel }: { message: string; onConfirm: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog ref={dialog} onCancel={(event) => { event.preventDefault(); onCancel(); }} aria-label="Confirm action" className="glass max-w-md p-7 text-ivory backdrop:bg-black/70">
      <p className="text-sm leading-relaxed">{message}</p>
      <div className="mt-6 flex justify-end gap-3">
        <button type="button" className="btn-glass" autoFocus onClick={onCancel}>Cancel</button>
        <button type="button" className="btn-primary" onClick={onConfirm}>Confirm</button>
      </div>
    </dialog>
  );
}
