'use client';

import { useEffect, useMemo, useState } from 'react';

type ClockBadgeProps = {
  language: 'ja' | 'en';
};

const pad2 = (value: number): string => String(value).padStart(2, '0');

export default function ClockBadge({ language }: ClockBadgeProps) {
  const [currentTime, setCurrentTime] = useState<Date>(() => new Date());
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const timerId = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => {
      window.clearInterval(timerId);
    };
  }, []);

  const locale = language === 'ja' ? 'ja-JP' : 'en-US';
  const weekday = useMemo(() => {
    if (!mounted) {
      return '---';
    }
    return currentTime.toLocaleDateString(locale, { weekday: 'short' });
  }, [currentTime, locale, mounted]);

  const dateText = mounted
    ? `${currentTime.getFullYear().toString().slice(-2)}/${pad2(currentTime.getMonth() + 1)}/${pad2(currentTime.getDate())} ${weekday}`
    : '--/--/-- ---';

  const timeText = mounted
    ? currentTime.toLocaleTimeString(locale, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    : '--:--:--';

  return (
    <div className="rounded-lg border border-white/15 bg-black/45 px-3 py-1.5 font-mono text-lg tabular-nums text-white shadow-lg backdrop-blur-md">
      <div className="text-md leading-6 opacity-90">{dateText}</div>
      <div className="text-2xl leading-12 opacity-90">{timeText}</div>
    </div>
  );
}

