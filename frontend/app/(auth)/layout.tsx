import { Wordmark } from "@/components/app-shell";

const POINTS = [
  { k: "01", t: "Check in daily", d: "Mood, energy, focus and sleep in under 20 seconds." },
  { k: "02", t: "It finds your patterns", d: "Correlations mined from your own data, not generic advice." },
  { k: "03", t: "It plans with you", d: "Predictions for tomorrow, with the reasons behind them." },
];

/** An example of the kind of insight the twin produces: shows the product, not decoration. */
function SampleInsight() {
  const bars = [
    { label: "Slept 6h+", value: 3.8, w: "76%", tone: "bg-foreground" },
    { label: "Under 6h", value: 2.4, w: "48%", tone: "bg-primary" },
  ];
  return (
    <figure
      aria-label="Example insight"
      className="max-w-md animate-fade-up rounded-lg border bg-card p-5 shadow-lift"
      style={{ animationDelay: "420ms" }}
    >
      <div className="flex items-center justify-between">
        <span className="eyebrow text-primary">Pattern found</span>
        <span className="font-mono text-[11px] text-muted-foreground">ρ = −0.62 · n = 34</span>
      </div>
      <p className="mt-3 text-[15px] font-semibold leading-snug">
        After nights under 6 hours, your next-day focus drops by more than a point.
      </p>
      <div className="mt-4 flex flex-col gap-2.5">
        {bars.map((b) => (
          <div key={b.label} className="grid grid-cols-[72px_1fr_28px] items-center gap-3 text-xs">
            <span className="text-muted-foreground">{b.label}</span>
            <div className="h-2 rounded-full bg-secondary">
              <div className={`h-full rounded-full ${b.tone}`} style={{ width: b.w }} />
            </div>
            <span className="text-right font-mono font-medium">{b.value}</span>
          </div>
        ))}
      </div>
      <figcaption className="mt-3 text-[11px] text-muted-foreground">
        Example. Average focus (1–5), from one user&apos;s own data.
      </figcaption>
    </figure>
  );
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel (desktop) */}
      <aside className="relative hidden overflow-hidden border-r bg-primary-soft lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <Wordmark />
        <div className="max-w-md animate-fade-up">
          <p className="eyebrow mb-4 text-primary">Your digital doppelgänger</p>
          <h1 className="text-[40px] font-semibold leading-[1.1] xl:text-[46px]">
            Know yourself,
            <br />
            by the numbers.
          </h1>
          <ul className="mt-10 flex flex-col gap-6">
            {POINTS.map((p, i) => (
              <li
                key={p.k}
                className="flex animate-fade-up gap-4"
                style={{ animationDelay: `${120 + i * 90}ms` }}
              >
                <span className="font-mono text-xs font-medium text-primary">{p.k}</span>
                <div>
                  <p className="font-semibold">{p.t}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">{p.d}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <SampleInsight />
        <p className="text-xs text-muted-foreground">
          Your data stays yours. Turn any source off, any time.
        </p>
      </aside>

      {/* Form */}
      <main className="flex flex-col px-5 py-8 sm:px-8">
        <div className="lg:hidden">
          <Wordmark />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[380px] animate-fade-up">{children}</div>
        </div>
      </main>
    </div>
  );
}
