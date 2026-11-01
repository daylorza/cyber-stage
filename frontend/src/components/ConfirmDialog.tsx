import { useEffect, useId, useRef } from "react";

export default function ConfirmDialog({ message, onConfirm, onCancel }: { message: string; onConfirm: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const messageId = useId();
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog ref={dialog} onCancel={(event) => { event.preventDefault(); onCancel(); }} aria-label="Confirm action" aria-describedby={messageId} className="glass m-auto w-[min(28rem,calc(100vw-2rem))] animate-fade-in p-6 text-ivory backdrop:bg-night/80 sm:p-7">
      <p id={messageId} className="text-sm leading-relaxed">{message}</p>
      <div className="mt-6 flex flex-wrap justify-end gap-3">
        <button type="button" className="btn-glass" autoFocus onClick={onCancel}>Cancel</button>
        <button type="button" className="btn-primary" onClick={onConfirm}>Confirm</button>
      </div>
    </dialog>
  );
}
