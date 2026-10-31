export type PlanRoom = { id: string; label?: string; d: string };

export type Plan = {
  outline: string;
  rooms: PlanRoom[];
  current: string;
  position: [number, number];
  /** Direction the view faces at rest, in degrees (0 = up the plan). */
  facing: number;
  details?: string[];
};

export type Residence = {
  id: string;
  city: string;
  collection: string;
  hero: string;
  plan: Plan;
};

/**
 * Seeded hero listings were removed: the home page no longer opens on
 * placeholder Miami / Los Angeles / New York residences. Every residence
 * shown comes from a real broker walkthrough upload.
 */
export const RESIDENCES: Residence[] = [];
