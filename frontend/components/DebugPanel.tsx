export function DebugPanel({
  debugItems,
  rawJson,
}: {
  debugItems: Array<{ label: string; value: string }>;
  rawJson: Record<string, unknown>;
}) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-text">AI Debug Console</h3>
          <p className="mt-1 text-sm text-text/70">Inspect intent, category, agent flow and structured payload details.</p>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {debugItems.map((item) => (
          <div key={item.label} className="rounded-3xl border border-secondary/20 bg-secondary/5 px-4 py-4">
            <p className="text-xs uppercase tracking-[0.28em] text-secondary">{item.label}</p>
            <p className="mt-2 text-base font-semibold text-text">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-[28px] border border-secondary/20 bg-slate-950/95 p-4 text-sm text-slate-100">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Raw JSON</p>
        <pre className="mt-3 max-h-56 overflow-auto text-xs leading-5 text-slate-100">
          {JSON.stringify(rawJson, null, 2)}
        </pre>
      </div>
    </div>
  );
}
