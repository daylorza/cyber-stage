export function createRadarSelection(select: (id: string) => void, hovered: () => string | undefined, delay = 150) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return {
    hover(id: string) {
      if (timer === undefined) select(id);
    },
    scroll() {
      clearTimeout(timer);
      timer = setTimeout(() => {
        timer = undefined;
        const id = hovered();
        if (id) select(id);
      }, delay);
    },
    dispose() {
      clearTimeout(timer);
      timer = undefined;
    },
  };
}
