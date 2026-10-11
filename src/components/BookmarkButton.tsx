'use client';

import React, { useState, useEffect } from 'react';
import { Bookmark } from 'lucide-react';

interface BookmarkButtonProps {
  postId: string;
}

export function BookmarkButton({ postId }: BookmarkButtonProps) {
  const [bookmarked, setBookmarked] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem('chronicle-bookmarks');
      if (stored) {
        const list = JSON.parse(stored);
        if (Array.isArray(list) && list.includes(postId)) {
          setBookmarked(true);
        }
      }
    } catch {
      // Fallback
    }
  }, [postId]);

  const toggleBookmark = () => {
    try {
      const stored = localStorage.getItem('chronicle-bookmarks');
      let list: string[] = stored ? JSON.parse(stored) : [];
      if (!Array.isArray(list)) list = [];

      if (bookmarked) {
        list = list.filter((id) => id !== postId);
        setBookmarked(false);
      } else {
        list.push(postId);
        setBookmarked(true);
      }

      localStorage.setItem('chronicle-bookmarks', JSON.stringify(list));
    } catch (e) {
      console.error('Bookmark error:', e);
    }
  };

  return (
    <button
      onClick={toggleBookmark}
      className="p-2.5 rounded-full border transition-all duration-200 cursor-pointer flex items-center justify-center hover:scale-105"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)',
        color: 'var(--text-main)'
      }}
      title={bookmarked ? 'Remove bookmark' : 'Bookmark this essay'}
    >
      <Bookmark
        className={`w-4 h-4 transition-colors ${
          bookmarked ? 'text-amber-600 fill-amber-600' : 'text-gray-400'
        }`}
      />
    </button>
  );
}
