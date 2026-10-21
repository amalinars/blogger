'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Timer,
  CheckCircle2,
  ArrowRight,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  Lock,
  Sparkles,
  Download
} from 'lucide-react';

interface CountdownGatewayProps {
  currentStep: number;
  totalSteps?: number;
  slug: string;
  destinationUrl?: string;
  durationSeconds?: number;
}

export function CountdownGateway({
  currentStep,
  totalSteps = 4,
  slug,
  destinationUrl = 'https://modapk.org/',
  durationSeconds = 8
}: CountdownGatewayProps) {
  const router = useRouter();
  const [secondsLeft, setSecondsLeft] = useState<number>(durationSeconds);
  const [isUnlocked, setIsUnlocked] = useState<boolean>(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Reset timer on step change
    setSecondsLeft(durationSeconds);
    setIsUnlocked(false);

    const timer = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setIsUnlocked(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [currentStep, durationSeconds]);

  // Smooth scroll to action box once countdown reaches 0
  useEffect(() => {
    if (isUnlocked && buttonRef.current) {
      buttonRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [isUnlocked]);

  const nextStep = currentStep + 1;
  const isFinalStep = currentStep >= totalSteps;
  const progressPercent = Math.max(0, Math.min(100, ((durationSeconds - secondsLeft) / durationSeconds) * 100));

  return (
    <div
      ref={buttonRef}
      className={`my-10 p-6 sm:p-8 rounded-2xl border transition-all duration-300 shadow-md ${
        isUnlocked
          ? 'border-emerald-500/60 shadow-emerald-500/10'
          : 'border-amber-500/50 shadow-amber-500/5'
      }`}
      style={{
        backgroundColor: 'var(--bg-card)'
      }}
    >
      <div className="flex flex-col items-center text-center max-w-xl mx-auto space-y-4">
        {/* Verification Status Pill */}
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-mono border"
          style={{
            borderColor: isUnlocked ? 'rgba(16, 185, 129, 0.4)' : 'rgba(245, 158, 11, 0.4)',
            backgroundColor: isUnlocked ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)',
            color: isUnlocked ? '#10b981' : '#f59e0b'
          }}
        >
          {isUnlocked ? (
            <>
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              <span className="font-semibold">Stage {currentStep} Verified Successfully</span>
            </>
          ) : (
            <>
              <Timer className="w-4 h-4 text-amber-500 animate-spin" />
              <span>Verifying Integrity Protocols • {secondsLeft}s</span>
            </>
          )}
        </div>

        {/* Main Headline */}
        <h3 className="text-xl sm:text-2xl font-serif font-bold" style={{ color: 'var(--text-main)' }}>
          {isFinalStep
            ? isUnlocked
              ? 'Destination Gateway Unlocked'
              : 'Generating Destination Handshake...'
            : isUnlocked
            ? `Layer ${currentStep} Audit Complete`
            : `Please Read & Wait ${secondsLeft} Seconds`}
        </h3>

        <p className="text-xs sm:text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {isFinalStep
            ? isUnlocked
              ? 'Security evaluation passed 100%. Click the verified button below to proceed to the target link at modapk.org.'
              : 'Finalizing security tokens and generating direct destination clearance...'
            : isUnlocked
            ? `Your inspection clearance for layer ${currentStep} is validated. Proceed to Layer ${nextStep} to continue the verification chain.`
            : `Our client-side validation engine is checking package signatures and SELinux sandboxing parameters while you read.`}
        </p>

        {/* Circular Progress & Countdown Counter */}
        {!isUnlocked && (
          <div className="py-2 flex flex-col items-center">
            <div className="relative w-24 h-24 flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  stroke="currentColor"
                  strokeWidth="6"
                  fill="transparent"
                  className="text-black/10 dark:text-white/10"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  stroke="#f59e0b"
                  strokeWidth="6"
                  strokeDasharray={264}
                  strokeDashoffset={264 - (264 * progressPercent) / 100}
                  strokeLinecap="round"
                  fill="transparent"
                  className="transition-all duration-300"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center font-mono">
                <span className="text-2xl font-bold text-amber-500">{secondsLeft}</span>
                <span className="text-[10px] uppercase text-neutral-400">SEC</span>
              </div>
            </div>
            <div className="w-48 bg-black/10 dark:bg-white/10 h-1.5 rounded-full mt-3 overflow-hidden">
              <div
                className="bg-amber-500 h-full transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}

        {/* Dynamic Action Button */}
        <div className="w-full pt-2">
          {!isUnlocked ? (
            <button
              disabled
              className="w-full sm:w-auto px-8 py-3.5 rounded-xl font-mono text-sm font-semibold opacity-60 cursor-not-allowed border flex items-center justify-center space-x-2 mx-auto"
              style={{
                backgroundColor: 'var(--bg-subtle)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-muted)'
              }}
            >
              <Lock className="w-4 h-4 text-amber-500/70" />
              <span>Please Wait ({secondsLeft}s)...</span>
            </button>
          ) : isFinalStep ? (
            <a
              href={destinationUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto px-9 py-4 rounded-xl font-mono text-sm font-bold text-white transition-all transform hover:scale-105 active:scale-95 shadow-lg flex items-center justify-center space-x-3 mx-auto cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                boxShadow: '0 8px 24px -4px rgba(16, 185, 129, 0.45)'
              }}
            >
              <Download className="w-5 h-5 animate-bounce" />
              <span>Get Link • Proceed to modapk.org</span>
              <ExternalLink className="w-4 h-4 ml-1 opacity-80" />
            </a>
          ) : (
            <Link
              href={`/post/${slug}?step=${nextStep}`}
              className="w-full sm:w-auto px-8 py-3.5 rounded-xl font-mono text-sm font-bold text-white transition-all transform hover:scale-105 active:scale-95 shadow-md flex items-center justify-center space-x-2 mx-auto cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                boxShadow: '0 8px 20px -4px rgba(245, 158, 11, 0.4)'
              }}
            >
              <span>Continue to Layer {nextStep}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          )}
        </div>

        {/* Security Assurance Footer */}
        <div className="flex items-center space-x-4 text-[10px] font-mono text-neutral-400 pt-2 border-t border-dashed w-full justify-center" style={{ borderColor: 'var(--border-subtle)' }}>
          <span>End-to-End Handshake</span>
          <span>•</span>
          <span>Zero Malicious Redirects</span>
          <span>•</span>
          <span>Verified Target: modapk.org</span>
        </div>
      </div>
    </div>
  );
}
