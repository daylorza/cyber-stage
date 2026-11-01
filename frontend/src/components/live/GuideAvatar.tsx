import "./guide-avatar.css";

type Props = { state?: "idle" | "thinking" | "speaking" | "nod"; excited?: boolean; large?: boolean };
const rings = [58.55, 86.48, 115.8, 147.88, 181.54, 214.15, 244.05, 272.06];
const outlines = [
  "M495.88 200 L470.33 240.60 L446.22 280.05 L400 286.75 L357.09 274.33 L316.97 247.94 L318.79 200 L319.95 153.78 L356.62 124.87 L400 114.18 L447.94 116.97 L470.33 159.40 Z",
  "M484.77 200 L476.10 243.94 L445.73 279.21 L400 281.85 L353.01 281.39 L326.59 242.39 L312.13 200 L320.79 154.27 L359.07 129.12 L400 106.02 L442.39 126.59 L476.10 156.06 Z",
  "M483.35 200 L482.21 247.46 L440.05 269.37 L400 289.92 L355.25 277.51 L327.82 241.68 L305.08 200 L330.63 159.95 L355.04 122.12 L400 110.50 L441.68 127.82 L482.21 152.54 Z",
  "M495.88 200 L470.33 240.60 L442.58 273.76 L400 293.69 L359.74 269.73 L316.97 247.94 L318.79 200 L326.24 157.42 L353.15 118.86 L400 119.49 L447.94 116.97 L470.33 159.40 Z",
  "M484.77 200 L470.53 240.72 L447.91 282.98 L400 280.38 L353.01 281.39 L326.59 242.39 L318.56 200 L317.02 152.09 L359.81 130.38 L400 106.02 L442.39 126.59 L470.53 159.28 Z",
];

export default function GuideAvatar({ state = "idle", excited = false, large = false }: Props) {
  const label = state === "thinking" ? "THINKING" : state === "speaking" ? "RESPONDING" : "GUIDE";
  return (
    <div role="img" aria-label="Guide visualizer" className={`guide-avatar guide-avatar--${state}${excited ? " guide-avatar--excited" : ""}${large ? " guide-avatar--large" : ""}`}>
      <svg aria-hidden="true" viewBox="200 0 400 400" className="guide-avatar__svg">
        <circle cx="400" cy="200" r="88" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
        <circle cx="400" cy="200" r="140" fill="none" stroke="rgba(255,255,255,0.02)" strokeWidth="1" />
        {rings.map((radius, i) => <circle key={radius} cx="400" cy="200" r={radius} fill="none" stroke="rgba(244,241,234,0.04)" strokeWidth="1" strokeDasharray={i % 2 ? "2 4" : "1 5"} />)}
        {Array.from({ length: 24 }, (_, i) => { const angle = i * Math.PI / 12; return <line key={i} x1={400 + 17.6 * Math.cos(angle)} y1={200 + 17.6 * Math.sin(angle)} x2={400 + 308 * Math.cos(angle)} y2={200 + 308 * Math.sin(angle)} stroke="rgba(244,241,234,0.03)" strokeWidth="1" />; })}
        <g className="guide-avatar__outlines" fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1">
          {outlines.map((path, i) => <path key={path} d={path} stroke={`rgba(244,241,234,${[.18, .14, .12, .08, .06][i]})`} />)}
        </g>
        {large && <text x="400" y="205" textAnchor="middle" fill="#ffffff" fontSize="14" fontWeight="500" letterSpacing="1">{label}</text>}
      </svg>
    </div>
  );
}
