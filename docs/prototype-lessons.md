# Prototype lessons and improvements

- Show the staged image directly when selecting furniture. The cascade and cutout outlines obscured the result; keep the camera framing fixed while changing styles.
- Offer “Choose furniture” immediately, so viewers can skip the walkthrough. Fade the style controls on hover-capable devices, while keeping them available to keyboard and touch users.
- A still image cannot follow a moving camera. The labeled box is a screen-space illustration only; future work needs camera tracking, occlusion, and properly anchored 3D furniture before claiming persistence during the walk.
- A style passing geometry checks may still contain no sofa or table. Require meaningful furniture for the room type and verify the result before presenting it as available. Never loosen geometry or privacy gates to make a style pass.
- Sit, coffee and drag-to-look remain TODOs until they provide the actual interaction. Separate residences must not inherit another city's facts, reservations or labels.
- Prototype assets and listing data are local and not committed. Document the running checkout and preserve source changes before restarting services.
