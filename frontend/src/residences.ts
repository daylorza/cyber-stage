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

/** Presentation for the seeded hero listings. Names, facts and prices come from the API. */
export const RESIDENCES: Residence[] = [
  {
    id: "seed_miami",
    city: "Miami",
    collection: "Private collection",
    hero: "/residences/miami.webp",
    plan: {
      outline: "M10 12 H112 Q184 34 190 128 H10 Z",
      rooms: [
        { id: "primary", label: "Primary suite", d: "M10 12 H66 V70 H10 Z" },
        { id: "living", label: "Living", d: "M66 12 H112 Q156 26 172 72 V98 H66 Z" },
        { id: "terrace", label: "Ocean terrace", d: "M112 12 Q184 34 190 128 H174 Q170 48 112 24 Z" },
        { id: "kitchen", d: "M10 70 H66 V128 H10 Z" },
        { id: "dining", d: "M66 98 H172 V128 H66 Z" },
      ],
      current: "living",
      position: [116, 58],
      facing: 90,
    },
  },
];

/** Cities shown grayed out in the Home menu: not live yet, so no link. */
export const UPCOMING_CITIES = ["Los Angeles", "New York"];
