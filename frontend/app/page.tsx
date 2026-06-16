'use client';

import { useState } from 'react';
import { Sidebar } from '../components/Sidebar';
import { ChatPanel } from '../components/ChatPanel';
import { DebugPanel } from '../components/DebugPanel';
import { dashboardData } from '../lib/dashboard-data';
import { Sparkles } from 'lucide-react';

export default function Home() {
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugItems, setDebugItems] = useState(dashboardData.debugItems);
  const [rawJson, setRawJson] = useState<Record<string, unknown>>(dashboardData.rawJson);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(108,99,255,0.18),transparent_25%),radial-gradient(circle_at_top_right,_rgba(79,70,229,0.14),transparent_22%),var(--bg-surface)] text-text">
      <div className="mx-auto grid min-h-screen max-w-[1800px] gap-6 px-4 py-6 lg:grid-cols-[280px_minmax(0,1.45fr)] xl:grid-cols-[280px_minmax(0,1.45fr)_360px]">
        <Sidebar menuItems={dashboardData.menuItems} />

        <section className="space-y-6">
          <div className="space-y-5 rounded-[32px] border border-white/80 bg-panel p-6 shadow-soft backdrop-blur-xl">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl space-y-3">
                <p className="text-sm uppercase tracking-[0.28em] text-secondary">Bookly AI Appointment Agent</p>
                <h1 className="text-3xl font-semibold md:text-4xl">A conversational salon booking assistant built around one chat.</h1>
                <p className="max-w-2xl text-sm leading-6 text-text/70 sm:text-base">
                  The entire product is chat-first. Bookly collects locations, services, salon preferences and appointment details through conversation only.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setDebugOpen((current) => !current)}
                className="inline-flex items-center justify-center rounded-3xl border border-secondary/20 bg-white/95 px-4 py-3 text-sm font-semibold text-text shadow-sm transition hover:border-primary/40 hover:bg-primary/10"
              >
                {debugOpen ? 'Hide debug' : 'Show debug'}
              </button>
            </div>

            <div className="flex flex-col gap-4 rounded-[28px] border border-secondary/20 bg-white/90 p-5 text-sm text-text/75 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-2">
                <p className="font-semibold text-text">Welcome to Bookly AI</p>
                <p>Start by asking about salons, services, or appointment policies and let the assistant guide the rest.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {dashboardData.prompts.map((prompt) => (
                  <span key={prompt} className="rounded-full border border-secondary/20 bg-secondary/5 px-3 py-2 text-xs font-medium uppercase tracking-[0.24em] text-text">
                    {prompt}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-3xl border border-secondary/20 bg-secondary/5 px-4 py-4">
                <p className="text-sm font-semibold text-text">Step 1</p>
                <p className="mt-2 text-sm text-text/70">Tell Bookly what you want. The assistant will ask follow-up questions naturally.</p>
              </div>
              <div className="rounded-3xl border border-secondary/20 bg-secondary/5 px-4 py-4">
                <p className="text-sm font-semibold text-text">Step 2</p>
                <p className="mt-2 text-sm text-text/70">Receive salon recommendations and book appointments directly inside the chat.</p>
              </div>
            </div>
          </div>

          <ChatPanel onDebugUpdate={(items, raw) => { setDebugItems(items); setRawJson(raw); }} />
        </section>

        {debugOpen ? (
          <aside className="space-y-6">
            <DebugPanel debugItems={debugItems} rawJson={rawJson} />
          </aside>
        ) : null}
      </div>
    </main>
  );
}
