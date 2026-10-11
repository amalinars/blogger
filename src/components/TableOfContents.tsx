'use client';

import React from 'react';
import { AlignLeft } from 'lucide-react';

interface TOCItem {
  id: string;
  text: string;
  level: number;
}

export function TableOfContents({ content }: { content: string }) {
  // Extract h2 and h3 headings from markdown content
  const headings: TOCItem[] = React.useMemo(() => {
    const lines = content.split('\n');
    const items: TOCItem[] = [];

    lines.forEach((line) => {
      const h2Match = line.match(/^##\s+(.+)$/);
      const h3Match = line.match(/^###\s+(.+)$/);

      if (h2Match) {
        const text = h2Match[1].trim();
        const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-');
        items.push({ id, text, level: 2 });
      } else if (h3Match) {
        const text = h3Match[1].trim();
        const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-');
        items.push({ id, text, level: 3 });
      }
    });

    return items;
  }, [content]);

  if (headings.length === 0) return null;

  return (
    <div
      className="p-5 rounded-xl border space-y-3"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)'
      }}
    >
      <div className="flex items-center space-x-2 text-xs font-mono font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
        <AlignLeft className="w-3.5 h-3.5" />
        <span>Table of Contents</span>
      </div>

      <nav className="space-y-1 text-xs">
        {headings.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className={`block py-1 hover:text-amber-600 transition-colors line-clamp-1 ${
              item.level === 3 ? 'pl-3 opacity-80' : 'font-medium'
            }`}
            style={{ color: 'var(--text-muted)' }}
          >
            {item.text}
          </a>
        ))}
      </nav>
    </div>
  );
}
