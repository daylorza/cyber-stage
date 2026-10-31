import { BRAND } from "../brand";

export default function BrandMark() {
  return (
    <span className="brand-mark inline-flex items-center gap-2.5">
      <svg viewBox="0 0 28 28" className="h-7 w-7 shrink-0" fill="none" aria-hidden="true">
        <path d="M4 24V7l10-4 10 4v17M9 24V11l5-2 5 2v13M2 24h24" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        <path d="M14 9v15" stroke="currentColor" strokeWidth="0.7" opacity="0.5" />
      </svg>
      <span>{BRAND}</span>
    </span>
  );
}
