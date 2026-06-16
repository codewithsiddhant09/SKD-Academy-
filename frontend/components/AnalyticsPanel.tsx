export function AnalyticsPanel({ analytics }: { analytics: Array<{ label: string; value: string }> }) {
  return (
    <div className="mt-6 rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <h3 className="text-lg font-semibold text-text">Analytics Dashboard</h3>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {analytics.map((item) => (
          <div key={item.label} className="rounded-3xl border border-secondary/20 bg-secondary/5 p-5 text-sm text-text">
            <p className="text-xs uppercase tracking-[0.28em] text-secondary">{item.label}</p>
            <p className="mt-3 text-2xl font-semibold text-text">{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
