import "./guide-avatar.css";

type Props = { state?: "idle" | "thinking" | "speaking" | "nod"; excited?: boolean; large?: boolean };
export default function GuideAvatar({ state = "idle", excited = false, large = false }: Props) {
  return (
    <div role="img" aria-label="Blue cloud-like guide bubble" className={`guide-avatar guide-avatar--${state}${excited ? " guide-avatar--excited" : ""}${large ? " guide-avatar--large" : ""}`}>
      <span className="guide-avatar__cloud guide-avatar__cloud--one" />
      <span className="guide-avatar__cloud guide-avatar__cloud--two" />
      <span className="guide-avatar__cloud guide-avatar__cloud--three" />
    </div>
  );
}
