'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Loader2, MapPin, Send, Sparkles } from 'lucide-react';
import { dashboardData } from '../lib/dashboard-data';
import { MarkdownMessage } from './MarkdownMessage';

type Recommendation = {
  vendor_id?: string;
  salon_name: string;
  rating?: number | null;
  location?: string;
  services?: string[];
  reason: string;
};

type ChatMessage = {
  id: string;
  role: 'assistant' | 'user';
  content: string;
  recommendations?: Recommendation[];
  source?: { document: string; confidence: string };
};

type DebugState = {
  intent: string;
  category: string;
  service: string;
  location: string;
  currentAgent: string;
  agentOutput: string;
  conversationState: string;
  apiResponses: string;
};

type ChatPanelProps = {
  onDebugUpdate?: (debugItems: Array<{ label: string; value: string }>, rawJson: Record<string, unknown>) => void;
};

const defaultDebugState: DebugState = {
  intent: 'Waiting for input',
  category: 'Waiting for input',
  service: 'Waiting for input',
  location: 'Waiting for input',
  currentAgent: 'Idle',
  agentOutput: 'Waiting for the first request',
  conversationState: 'Ready',
  apiResponses: 'No activity yet',
};

const suggestionChips = ['I want hair smoothing', 'I need bridal makeup', 'Find salons near me', 'What is cancellation policy'];

const initialMessages: ChatMessage[] = [
  {
    id: 'assistant-welcome',
    role: 'assistant',
    content:
      'Welcome to Bookly.\n\nI am your AI appointment assistant, here to help you discover salons, answer your questions, and book appointments.\n\nHow may I assist you today?',
  },
];

export function ChatPanel({ onDebugUpdate }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debugState, setDebugState] = useState<DebugState>(defaultDebugState);
  const [rawJson, setRawJson] = useState<Record<string, unknown>>({});
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const sessionId = useMemo(() => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return `session-${Math.random().toString(36).slice(2)}`;
  }, []);

  const debugItems = useMemo(
    () => [
      { label: 'Intent', value: debugState.intent },
      { label: 'Category', value: debugState.category },
      { label: 'Service', value: debugState.service },
      { label: 'Location', value: debugState.location },
      { label: 'Current Agent', value: debugState.currentAgent },
      { label: 'Agent Output', value: debugState.agentOutput },
      { label: 'Conversation State', value: debugState.conversationState },
      { label: 'API Responses', value: debugState.apiResponses },
    ],
    [debugState],
  );

  useEffect(() => {
    const stored = window.localStorage.getItem('bookly-ai-conversation');
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as ChatMessage[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      } catch {
        // ignore invalid history
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem('bookly-ai-conversation', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    onDebugUpdate?.(debugItems, rawJson);
  }, [debugItems, onDebugUpdate, rawJson]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function sendMessage(message: string) {
    if (!message.trim()) {
      return;
    }

    setError(null);
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: 'user', content: message }]);
    setInput('');
    setLoading(true);
    setDebugState((current) => ({
      ...current,
      currentAgent: 'Intent Agent',
      agentOutput: 'Detecting service intent',
      conversationState: 'Analyzing request',
      apiResponses: 'Calling backend services',
    }));

    const assistantId = `assistant-${Date.now()}`;
    setMessages((current) => [...current, { id: assistantId, role: 'assistant', content: '' }]);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          // Optional: open the page with ?user_id=<Mongo user _id> to chat as a signed-in customer.
          user_id: new URLSearchParams(window.location.search).get('user_id'),
          message,
          history: messages.map((message) => ({ role: message.role, content: message.content })),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || 'Unable to reach chat API');
      }

      const contentType = response.headers.get('content-type') ?? '';
      let reply = '';
      let recommendations: Recommendation[] | undefined;
      let source: { document: string; confidence: string } | undefined;
      let rawPayload: Record<string, unknown> = {};

      if (contentType.includes('application/json')) {
        const data = await response.json();
        reply = data.reply || data.answer || 'Sorry, I could not process that request.';
        recommendations = Array.isArray(data.recommendations) ? data.recommendations : undefined;
        source = data.source ? { document: data.source.document || data.source.source, confidence: data.source.confidence || '' } : undefined;
        rawPayload = data;
      } else if (response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let result = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          result += decoder.decode(value, { stream: true });
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId ? { ...item, content: result } : item,
            ),
          );
        }

        reply = result.trim();
        rawPayload = { text: result };
      } else {
        reply = await response.text();
        rawPayload = { text: reply };
      }

      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                content: reply,
                recommendations,
                source,
              }
            : item,
        ),
      );

      setDebugState((current) => ({
        intent: rawPayload?.intent?.toString() || current.intent,
        category: rawPayload?.category?.toString() || current.category,
        service: rawPayload?.service?.toString() || current.service,
        location: rawPayload?.location?.toString() || current.location,
        currentAgent: rawPayload?.currentAgent?.toString() || 'Salon Search Agent',
        agentOutput: reply.slice(0, 120),
        conversationState: recommendations ? 'Recommendation delivered' : 'Response delivered',
        apiResponses: JSON.stringify(rawPayload, null, 2),
      }));
      setRawJson(rawPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error');
      setDebugState((current) => ({
        ...current,
        currentAgent: 'Error',
        agentOutput: err instanceof Error ? err.message : 'Unexpected error',
        conversationState: 'Failed to complete request',
        apiResponses: err instanceof Error ? err.message : 'Unexpected error',
      }));
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(input);
  }

  function handleQuickAction(action: string) {
    sendMessage(action);
  }

  function handleRecommendationAction(recommendation: Recommendation) {
    sendMessage(`Book ${recommendation.salon_name}`);
  }

  const stepItems = [
    { label: 'Intent Detection', active: debugState.currentAgent.includes('Intent') || debugState.conversationState !== 'Ready' },
    { label: 'Location Analysis', active: debugState.location !== 'Waiting for input' },
    { label: 'Salon Search', active: debugState.currentAgent.includes('Salon') || debugState.conversationState === 'Recommendation delivered' },
    { label: 'Recommendation', active: debugState.conversationState === 'Recommendation delivered' },
  ];

  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.28em] text-secondary">Chat</p>
          <h3 className="text-xl font-semibold text-text">Bookly AI conversation</h3>
        </div>
        <span className="inline-flex items-center gap-2 rounded-3xl bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-primary">
          <Sparkles className="h-4 w-4" />
          Conversational first
        </span>
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        {dashboardData.categories.map((category) => (
          <span
            key={category}
            className="rounded-full border border-secondary/20 bg-secondary/5 px-3 py-2 text-xs font-semibold text-text uppercase tracking-[0.24em]"
          >
            {category}
          </span>
        ))}
      </div>

      <div className="space-y-4 rounded-[28px] border border-secondary/20 bg-slate-950/95 p-4 text-sm text-slate-100 shadow-sm">
        {stepItems.map((step) => (
          <div key={step.label} className="flex items-center gap-3 rounded-3xl bg-slate-900/95 px-4 py-3">
            <span className={step.active ? 'text-emerald-400' : 'text-slate-600'}>
              <CheckCircle2 className="h-4 w-4" />
            </span>
            <span className={step.active ? 'text-slate-100' : 'text-slate-400'}>{step.label}</span>
          </div>
        ))}
      </div>

      <div className="max-h-[62vh] space-y-4 overflow-y-auto rounded-[28px] border border-secondary/20 bg-slate-950/95 p-4 text-sm text-slate-100 shadow-sm">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`rounded-3xl p-4 ${message.role === 'assistant' ? 'bg-slate-900/95 text-slate-100' : 'ml-auto max-w-[85%] bg-white text-text'}`}
          >
            <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{message.role === 'assistant' ? 'Bookly AI' : 'You'}</p>
            {message.role === 'assistant' ? (
              <MarkdownMessage content={message.content} variant="assistant" />
            ) : (
              <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{message.content}</p>
            )}

            {message.recommendations?.length ? (
              <div className="mt-4 space-y-4">
                {message.recommendations.map((recommendation) => (
                  <div key={recommendation.vendor_id ?? recommendation.salon_name} className="rounded-[24px] border border-secondary/20 bg-white p-4 text-text">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="font-semibold">{recommendation.salon_name}</p>
                        {recommendation.services?.length ? (
                          <p className="mt-1 text-sm text-slate-600">{recommendation.services.join(' · ')}</p>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                        {recommendation.rating ? <span>⭐ {recommendation.rating}</span> : null}
                        {recommendation.location ? (
                          <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{recommendation.location}</span>
                        ) : null}
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-slate-600">{recommendation.reason}</p>
                    <button
                      type="button"
                      onClick={() => handleRecommendationAction(recommendation)}
                      className="mt-4 inline-flex items-center justify-center rounded-3xl bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary/90"
                    >
                      Book This Salon
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            {message.source ? (
              <div className="mt-4 rounded-3xl border border-slate-800 bg-slate-900 p-4 text-xs text-slate-300">
                <p className="font-semibold text-slate-100">Source</p>
                <p className="mt-2">{message.source.document}</p>
                <p className="mt-1 text-slate-500">Confidence: {message.source.confidence}</p>
              </div>
            ) : null}
          </div>
        ))}
        <div ref={messageEndRef} />
      </div>

      {error ? <p className="rounded-3xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

      <form onSubmit={handleSubmit} className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type your message and press Enter..."
          className="w-full rounded-3xl border border-secondary/20 bg-white px-4 py-3 text-sm text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
        />
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center rounded-3xl bg-primary px-6 py-3 text-sm font-semibold text-white transition hover:bg-primary/95 disabled:cursor-not-allowed disabled:opacity-70"
        >
          <Send className="mr-2 h-4 w-4" />
          {loading ? 'Thinking…' : 'Send'}
        </button>
      </form>

      <div className="mt-4 flex flex-wrap gap-3">
        {suggestionChips.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() => handleQuickAction(chip)}
            className="rounded-full border border-secondary/20 bg-secondary/5 px-4 py-2 text-sm font-medium text-text shadow-sm transition hover:border-primary/40 hover:bg-primary/10"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}
