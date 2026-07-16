import { motion } from "motion/react";
import { cardReveal } from "../lib/motion";

export function SkeletonCard() {
  return (
    <motion.div
      {...cardReveal}
      data-testid="skeleton"
      className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div className="flex items-center gap-3">
        <div className="size-10 rounded-full shimmer" />
        <div className="h-4 w-40 rounded shimmer" />
      </div>
      <div className="mt-4 aspect-video w-full rounded-xl shimmer" />
      <div className="mt-4 flex gap-2">
        <div className="h-10 w-28 rounded-xl shimmer" />
        <div className="h-10 w-28 rounded-xl shimmer" />
      </div>
    </motion.div>
  );
}
