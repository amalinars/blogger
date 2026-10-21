'use client';

import React from 'react';
import Link from 'next/link';
import { CheckCircle2, ShieldCheck, Cpu, Lock, DownloadCloud } from 'lucide-react';

interface StepProgressBarProps {
  currentStep: number;
  slug: string;
}

const STEPS = [
  { step: 1, title: 'Manifest Audit', short: 'Step 1', icon: ShieldCheck },
  { step: 2, title: 'Bytecode Inspection', short: 'Step 2', icon: Cpu },
  { step: 3, title: 'Security Sandbox', short: 'Step 3', icon: Lock },
  { step: 4, title: 'Destination Link', short: 'Step 4', icon: DownloadCloud }
];

export function StepProgressBar({ currentStep, slug }: StepProgressBarProps) {
  return (
    <div
      className="w-full my-6 p-4 sm:p-5 rounded-2xl border transition-all duration-300 shadow-sm"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)'
      }}
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] font-mono uppercase tracking-widest text-emerald-600 dark:text-emerald-400 font-bold">
              Multi-Layer Gateway Protocol
            </span>
          </div>
          <h3 className="text-sm sm:text-base font-serif font-bold mt-0.5" style={{ color: 'var(--text-main)' }}>
            Stage {currentStep} of 4: {STEPS[currentStep - 1]?.title || 'Package Verification'}
          </h3>
        </div>

        <span className="px-2.5 py-1 rounded-full text-[10px] font-mono border self-start sm:self-auto" style={{ borderColor: 'var(--border-strong)', color: 'var(--text-muted)' }}>
          {currentStep === 4 ? 'Ready for Handoff' : `${4 - currentStep} layer(s) remaining`}
        </span>
      </div>

      {/* Steps Visual Ribbon */}
      <div className="grid grid-cols-4 gap-2 sm:gap-3">
        {STEPS.map((s) => {
          const isDone = s.step < currentStep;
          const isActive = s.step === currentStep;
          const isPending = s.step > currentStep;
          const Icon = s.icon;

          return (
            <div
              key={s.step}
              className={`p-2.5 sm:p-3 rounded-xl border flex flex-col justify-between transition-all duration-200 ${
                isActive
                  ? 'border-amber-500/70 shadow-xs bg-amber-500/5 dark:bg-amber-500/10'
                  : isDone
                  ? 'border-emerald-500/50 bg-emerald-500/5'
                  : 'opacity-60 border-dashed'
              }`}
              style={{
                borderColor: isActive ? 'var(--accent)' : undefined
              }}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-mono font-semibold" style={{ color: isActive ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {s.short}
                </span>
                {isDone ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-amber-500 dark:text-amber-400 animate-bounce' : 'opacity-40'}`} />
                )}
              </div>

              <div className="text-[11px] font-serif font-medium leading-tight truncate hidden sm:block" style={{ color: 'var(--text-main)' }}>
                {s.title}
              </div>

              {/* Progress mini indicator */}
              <div className="w-full bg-black/10 dark:bg-white/10 h-1 rounded-full mt-2 overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    isDone ? 'w-full bg-emerald-500' : isActive ? 'w-full bg-amber-500 animate-pulse' : 'w-0'
                  }`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
