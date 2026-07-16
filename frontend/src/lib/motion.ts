export const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];

export const fadeRise = (order: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, ease: EASE_OUT, delay: order * 0.06 },
});

export const cardReveal = {
  initial: { opacity: 0, y: 12, scale: 0.99 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.32, ease: EASE_OUT },
};

export const cascade = (order: number) => ({
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: EASE_OUT, delay: 0.08 + order * 0.05 },
});
