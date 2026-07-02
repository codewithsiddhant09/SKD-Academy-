'use client';

import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type MarkdownMessageProps = {
  content: string;
  variant?: 'assistant' | 'user';
};

function buildComponents(variant: 'assistant' | 'user'): Components {
  const isAssistant = variant === 'assistant';

  return {
    p: ({ children }) => (
      <p className={`mb-3 last:mb-0 leading-7 ${isAssistant ? 'text-slate-100' : 'text-text'}`}>
        {children}
      </p>
    ),
    strong: ({ children }) => (
      <strong className={`font-semibold ${isAssistant ? 'text-white' : 'text-text'}`}>{children}</strong>
    ),
    em: ({ children }) => <em className="italic">{children}</em>,
    h1: ({ children }) => (
      <h1 className={`mb-3 mt-4 text-xl font-bold first:mt-0 ${isAssistant ? 'text-white' : 'text-text'}`}>
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className={`mb-3 mt-4 text-lg font-semibold first:mt-0 ${isAssistant ? 'text-white' : 'text-text'}`}>
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className={`mb-2 mt-3 text-base font-semibold first:mt-0 ${isAssistant ? 'text-white' : 'text-text'}`}>
        {children}
      </h3>
    ),
    ul: ({ children }) => (
      <ul className={`mb-3 list-disc space-y-1 pl-5 last:mb-0 ${isAssistant ? 'text-slate-100' : 'text-text'}`}>
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className={`mb-3 list-decimal space-y-1 pl-5 last:mb-0 ${isAssistant ? 'text-slate-100' : 'text-text'}`}>
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="leading-7">{children}</li>,
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
      >
        {children}
      </a>
    ),
    blockquote: ({ children }) => (
      <blockquote
        className={`mb-3 border-l-4 pl-4 italic last:mb-0 ${
          isAssistant ? 'border-slate-600 text-slate-300' : 'border-secondary/40 text-text/70'
        }`}
      >
        {children}
      </blockquote>
    ),
    code: ({ className, children }) => {
      const isBlock = Boolean(className);
      if (isBlock) {
        return <code className={className}>{children}</code>;
      }
      return (
        <code
          className={`rounded px-1.5 py-0.5 font-mono text-[0.85em] ${
            isAssistant ? 'bg-slate-800 text-emerald-300' : 'bg-secondary/10 text-text'
          }`}
        >
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre
        className={`mb-3 overflow-x-auto rounded-2xl p-4 font-mono text-xs last:mb-0 ${
          isAssistant ? 'bg-slate-800 text-emerald-300' : 'bg-slate-100 text-text'
        }`}
      >
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="mb-3 overflow-x-auto last:mb-0">
        <table className="min-w-full border-collapse text-left text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className={isAssistant ? 'bg-slate-800 text-slate-100' : 'bg-secondary/10 text-text'}>
        {children}
      </thead>
    ),
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => (
      <tr className={`border-b ${isAssistant ? 'border-slate-700' : 'border-secondary/20'}`}>{children}</tr>
    ),
    th: ({ children }) => <th className="px-3 py-2 font-semibold">{children}</th>,
    td: ({ children }) => <td className="px-3 py-2">{children}</td>,
    hr: () => <hr className={`my-4 ${isAssistant ? 'border-slate-700' : 'border-secondary/20'}`} />,
  };
}

export function MarkdownMessage({ content, variant = 'assistant' }: MarkdownMessageProps) {
  if (!content) {
    return null;
  }

  return (
    <div className="mt-3 text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildComponents(variant)}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
