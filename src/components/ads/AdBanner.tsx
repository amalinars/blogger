'use client';

import React, { useState, useEffect } from 'react';

interface AdBannerProps {
  adKey: string;
  width: number;
  height: number;
  className?: string;
  label?: string;
  autoRefresh?: boolean;
  refreshInterval?: number; // in seconds
}

import { HilltopBanner } from './HilltopBanner';

export function AdBanner({
  className = '',
  label = 'Advertisement'
}: Partial<AdBannerProps>) {
  return <HilltopBanner className={className} label={label} />;
}

export { AD_CONFIG } from '@/lib/ad-config';
