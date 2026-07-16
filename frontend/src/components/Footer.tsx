export function Footer() {
  return (
    <footer className="w-full max-w-2xl border-t border-zinc-200 py-8 text-sm text-zinc-500 dark:border-zinc-800">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          No popups. No fake buttons. No tracking.{" "}
          <a className="link-sweep text-cyan-500" href="https://github.com/OWNER/savevidai">
            Open source
          </a>
          .
        </p>
        <a className="link-sweep" href="https://ko-fi.com/OWNER">
          Support this project
        </a>
      </div>
    </footer>
  );
}
