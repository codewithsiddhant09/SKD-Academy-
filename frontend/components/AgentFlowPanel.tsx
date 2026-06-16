export function AgentFlowPanel({ agents, activeIndex }: { agents: string[]; activeIndex: number }) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <h3 className="text-lg font-semibold text-text">Agent Flow</h3>
      <div className="mt-5 grid gap-4">
        {agents.map((agent, index) => (
          <div
            key={agent}
            className={`rounded-3xl px-4 py-4 ${index === activeIndex ? 'border border-primary bg-primary/10 text-primary' : 'border border-secondary/20 bg-secondary/5 text-text'}`}
          >
            <p className="text-xs uppercase tracking-[0.25em] text-secondary">{agent}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
