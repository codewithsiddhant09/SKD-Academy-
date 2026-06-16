const toneClasses: Record<string, string> = {
  emerald: 'text-emerald-700',
  amber: 'text-amber-700',
  blue: 'text-sky-700',
};

export function ApiMonitorPanel({ apiStats }: { apiStats: Array<{ label: string; status: string; response: string; tone: string }> }) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/80 p-6 shadow-soft">
      <h3 className="text-lg font-semibold text-text">API Monitor</h3>
      <div className="mt-4 space-y-3 text-sm text-text/70">
        {apiStats.map((stat) => (
          <div key={stat.label} className="rounded-3xl bg-primary/5 p-4">
            <p className="font-semibold text-text">{stat.label}</p>
            <p className="mt-1">Status: <span className={`font-semibold ${toneClasses[stat.tone] ?? 'text-text'}`}>{stat.status}</span></p>
            <p>{stat.response}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
