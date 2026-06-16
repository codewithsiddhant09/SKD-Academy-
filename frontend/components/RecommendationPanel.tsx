export function RecommendationPanel({ recommendations }: { recommendations: Array<{ name: string; rating: string; distance: string; services: string[]; hours: string; reason: string }> }) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.28em] text-secondary">Salon Recommendations</p>
          <h3 className="text-xl font-semibold text-text">Top picks</h3>
        </div>
        <button className="rounded-3xl bg-secondary/10 px-4 py-2 text-sm font-semibold text-secondary">Refresh</button>
      </div>
      <div className="mt-6 space-y-4">
        {recommendations.map((card) => (
          <div key={card.name} className="rounded-[32px] border border-secondary/20 bg-secondary/5 p-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-lg font-semibold text-text">{card.name}</p>
                <p className="mt-2 text-sm text-text/70">{card.services.join(' • ')}</p>
              </div>
              <div className="flex items-center gap-3 text-sm text-text/70">
                <span className="rounded-2xl bg-white/90 px-3 py-2">{card.rating} ★</span>
                <span className="rounded-2xl bg-white/90 px-3 py-2">{card.distance}</span>
              </div>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-3xl bg-white px-4 py-4 text-sm text-text/70">Open Hours: {card.hours}</div>
              <div className="rounded-3xl bg-white px-4 py-4 text-sm text-text/70">Recommended because: {card.reason}</div>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button className="rounded-3xl bg-primary px-4 py-2 text-sm font-semibold text-white">Book</button>
              <button className="rounded-3xl border border-secondary/60 bg-white px-4 py-2 text-sm font-semibold text-text">View Details</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
