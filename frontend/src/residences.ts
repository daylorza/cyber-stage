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
    hero: "/residences/miami.png",
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
  {
    id: "seed_los_angeles",
    city: "Los Angeles",
    collection: "Private collection",
    hero: "/residences/los-angeles.png",
    plan: {
      outline: "M10 20 H190 V120 H10 Z",
      rooms: [
        { id: "primary", label: "Primary suite", d: "M10 20 H62 V84 H10 Z" },
        { id: "living", label: "Living", d: "M62 20 H150 V84 H62 Z" },
        { id: "kitchen", d: "M150 20 H190 V84 H150 Z" },
        { id: "terrace", label: "Pool terrace", d: "M10 84 H190 V120 H10 Z" },
      ],
      details: ["M72 94 H182 V112 H72 Z"],
      current: "living",
      position: [104, 52],
      facing: 150,
    },
  },
  {
    id: "seed_london",
    city: "London",
    collection: "Private collection",
    hero: "/residences/london.jpg",
    plan: {
      outline: "M10 14 H190 V126 H10 Z",
      rooms: [
        { id: "living", label: "Living room", d: "M10 14 H128 V92 H10 Z" },
        { id: "primary", label: "Primary suite", d: "M128 14 H190 V78 H128 Z" },
        { id: "dining", d: "M128 78 H190 V126 H128 Z" },
        { id: "terrace", label: "Terrace", d: "M10 92 H128 V126 H10 Z" },
      ],
      details: ["M16 19 H122"],
      current: "living",
      position: [62, 66],
      facing: 8,
    },
  },
];
