export function FaqPolicyPanel({ faqItems }: { faqItems: Array<{ question: string; answer: string; source: string; confidence: string }> }) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.28em] text-secondary">FAQ / Policy</p>
          <h3 className="text-xl font-semibold text-text">Knowledge answers</h3>
        </div>
        <button className="rounded-3xl bg-secondary/10 px-4 py-2 text-sm font-semibold text-secondary">View sources</button>
      </div>
      <div className="mt-6 space-y-4">
        {faqItems.map((item) => (
          <div key={item.question} className="rounded-[28px] border border-secondary/20 bg-secondary/5 p-4">
            <p className="font-semibold text-text">Question</p>
            <p className="mt-2 text-sm text-text/70">{item.question}</p>
            <p className="mt-3 text-sm text-text/70">Answer: {item.answer}</p>
            <p className="mt-3 text-xs uppercase tracking-[0.24em] text-secondary">Source: {item.source} | Confidence: {item.confidence}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
