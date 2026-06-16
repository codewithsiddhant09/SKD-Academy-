export function CategoryGrid({ categories }: { categories: string[] }) {
  return (
    <div className="rounded-[32px] border border-white/80 bg-white/80 p-6 shadow-soft">
      <h3 className="text-lg font-semibold text-text">Categories</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {categories.map((item) => (
          <button key={item} className="rounded-[24px] border border-secondary/20 bg-secondary/5 px-4 py-4 text-left text-sm font-medium text-text transition hover:border-primary/40 hover:bg-primary/10">
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
