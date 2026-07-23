import { useEffect, useState } from "react";
import { getMaintenance, setMaintenance, type Maintenance } from "./api";

// Live site kill-switch. Reads the current maintenance flag on mount and lets
// the admin flip it. Kept fully self-contained so a failing status call can
// never take the surrounding dashboard down with it.
export function SiteControls() {
  const [state, setState] = useState<Maintenance | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(false);

  useEffect(() => {
    let alive = true;
    getMaintenance()
      .then((m) => {
        if (alive) setState(m);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function apply(on: boolean) {
    setBusy(true);
    setActionError(false);
    try {
      const next = await setMaintenance(on);
      setState(next);
    } catch {
      // Keep the last known state so the panel stays honest on failure.
      setActionError(true);
    } finally {
      setBusy(false);
    }
  }

  function onToggle() {
    if (!state) return;
    if (state.on) {
      // Going live is safe and reversible, so skip the extra friction.
      void apply(false);
    } else if (window.confirm("This shows the maintenance page to everyone. Continue?")) {
      void apply(true);
    }
  }

  return (
    <div className="panel p-4">
      <h2 className="font-semibold">Site controls</h2>

      {state === null && !loadFailed && <p className="mt-3 text-sm text-[var(--muted)]">Checking...</p>}

      {loadFailed && <p className="mt-3 text-sm text-[var(--muted)]">Could not load site status</p>}

      {state && (
        <>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className="inline-block size-2.5 rounded-full"
              style={{ background: state.on ? "#f59e0b" : "#22c55e" }}
            />
            <span>{state.on ? "In maintenance" : "Live"}</span>
          </div>

          <button
            type="button"
            className="btn mt-3 w-full"
            onClick={onToggle}
            disabled={busy || state.forced_by_env}
          >
            {busy ? "Working..." : state.on ? "Turn off, go live" : "Enable maintenance"}
          </button>

          {state.forced_by_env && (
            <p className="mt-3 text-sm text-[var(--muted)]">
              Held on by the MAINTENANCE_MODE variable. Clear it in Render to unlock this.
            </p>
          )}

          {actionError && <p className="mt-3 text-sm text-[#ff453a]">Could not update, try again.</p>}
        </>
      )}
    </div>
  );
}
