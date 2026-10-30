import type { WalkStop } from "../../api";
import type { Plan } from "../../residences";

/**
 * A schematic plan for an uploaded walkthrough: the rooms of the video in walking order, laid out as a
 * snake (left to right, then back). Not a measured floor plan — the nav labels it "not to scale".
 */
export function schematicPlan(stops: { id: string; name: string; main?: boolean }[], current: string): Plan | null {
  if (stops.length === 0) return null;
  const cols = Math.max(1, Math.ceil(stops.length / 2));
  const top = 14;
  const height = 56;
  const width = 180 / cols;
  const rooms = stops.map((s, i) => {
    const row = i < cols ? 0 : 1;
    const col = row === 0 ? i : cols - 1 - (i - cols);
    const x = 10 + col * width;
    const y = top + row * height;
    return { id: s.id, label: s.name, d: `M${x} ${y} H${x + width} V${y + height} H${x} Z`, cx: x + width / 2, cy: y + height / 2 };
  });
  const here = rooms.find((r) => r.id === current) ?? rooms[0];
  return {
    outline: `M10 ${top} H190 V${top + (stops.length > cols ? 2 : 1) * height} H10 Z`,
    rooms: rooms.map(({ id, label, d }) => ({ id, label, d })),
    current: here.id,
    position: [here.cx, here.cy],
    facing: 0,
  };
}

export const stopsForPlan = (path: WalkStop[]) => path.map((p) => ({ id: p.id, name: p.name, main: p.main }));
