/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface DrugKeyword {
  id: string;
  word: string;
  category: 'traditional' | 'cannabis' | 'amphetamine' | 'cnb' | 'cathinone' | 'fentanyl' | 'hallucinogens' | 'psychotropic' | 'precursors' | 'actions';
  translation: string;
  language: 'mn' | 'en' | 'ru';
}

export interface TargetSite {
  id: string;
  name: string;
  url: string;
  queryDomain: string;
  category: 'enforcement' | 'government' | 'health' | 'education' | 'ngo' | 'media' | 'international';
}

export interface NewsArticle {
  id: string;
  title: string;          // Chinese translation of the title
  originalTitle: string;  // Original title in Mongolian, English, or Russian
  url: string;            // Source link
  date: string;           // Date of news (relative or exact YYYY-MM-DD)
  siteName: string;       // Name of source site
  siteUrl: string;        // Domain of source site
  category: string;       // Matched drug category (e.g., 大麻, 安纳咖, 芬太尼, 传统毒品, 易制毒化学品等)
  riskLevel: 'High' | 'Medium' | 'Low'; // Automatically classified risk level
  summary: string;        // Analytical summary of the article in Chinese
  entities: {
    locations: string[];
    organizations: string[];
    suspects?: string;
  };
  details?: {
    seizureAmount?: string; // Seized volume/amount
    traffickingRoute?: string; // Detected smuggling route
    penalties?: string; // Law enforcement actions/sentences
  };
  matchedKeywords: string[]; // Keywords found in the article
}

export interface SearchConfig {
  selectedSiteCategories: string[];
  selectedKeywords: string[];
  timeRange: 'day' | 'week' | 'month';
  customQuery?: string;
}

export interface MonitoringStats {
  byCategory: { name: string; value: number }[];
  bySite: { name: string; value: number }[];
  byRisk: { name: string; value: number }[];
  byDate: { name: string; count: number }[];
}
