type EventType = "visit" | "download";

/** Fire-and-forget analytics beacon. No personal data, never throws, never blocks. */
export function sendEvent(type: EventType, quality?: string): void {
  const body = JSON.stringify(quality ? { type, quality } : { type });
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon("/api/event", new Blob([body], { type: "application/json" }));
      return;
    }
    void fetch("/api/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // analytics must never affect the user
  }
}
