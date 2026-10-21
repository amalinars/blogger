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

export function AdBanner({
  adKey,
  className = '',
  label = 'Advertisement'
}: AdBannerProps) {
  // Adsterra disabled — ready for Monetag integration
  return null;
}

export { AD_CONFIG } from '@/lib/ad-config';
