/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useMemo } from 'react';
import { TARGET_SITES, CATEGORY_NAMES } from '../data/sites';
import { TargetSite } from '../types';
import { Shield, Eye, Globe, Landmark, HeartPulse, GraduationCap, Users, Newspaper, Check, Square, CheckSquare } from 'lucide-react';

interface SiteSelectorProps {
  selectedCategories: string[];
  onChange: (categories: string[]) => void;
}

export default function SiteSelector({ selectedCategories, onChange }: SiteSelectorProps) {
  
  const categories = useMemo(() => {
    return Object.keys(CATEGORY_NAMES) as (keyof typeof CATEGORY_NAMES)[];
  }, []);

  const toggleCategory = (category: string) => {
    if (selectedCategories.includes(category)) {
      onChange(selectedCategories.filter(c => c !== category));
    } else {
      onChange([...selectedCategories, category]);
    }
  };

  const selectAll = () => {
    onChange(categories);
  };

  const clearAll = () => {
    onChange([]);
  };

  // Assign standard vector icons for each site category
  const getCategoryIcon = (cat: string) => {
    switch (cat) {
      case 'enforcement':
        return <Shield className="w-4 h-4 text-slate-600" />;
      case 'government':
        return <Landmark className="w-4 h-4 text-slate-600" />;
      case 'health':
        return <HeartPulse className="w-4 h-4 text-slate-600" />;
      case 'education':
        return <GraduationCap className="w-4 h-4 text-slate-600" />;
      case 'ngo':
        return <Users className="w-4 h-4 text-slate-600" />;
      case 'media':
        return <Newspaper className="w-4 h-4 text-slate-600" />;
      case 'international':
        return <Globe className="w-4 h-4 text-slate-600" />;
      case 'china':
        return <Shield className="w-4 h-4 text-emerald-600" />;
      default:
        return <Globe className="w-4 h-4 text-slate-600" />;
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-150 shadow-sm overflow-hidden" id="site-selector-panel">
      {/* Header */}
      <div className="p-4 bg-gradient-to-r from-slate-50 to-slate-100 border-b border-slate-150 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Eye className="w-5 h-5 text-slate-600" />
          <h2 className="text-base font-semibold text-slate-800">
            监测信源管控范围 (Surveillance Perimeter)
          </h2>
          <span className="bg-slate-200 text-slate-700 text-xs px-2.5 py-0.5 rounded-full font-medium">
            监测中: {selectedCategories.length === 0 ? '全部 22' : `${TARGET_SITES.filter(s => selectedCategories.includes(s.category)).length}`} 个站点
          </span>
        </div>

        {/* Global toggles */}
        <div className="flex gap-2">
          <button
            onClick={selectAll}
            className="text-xs px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 rounded border border-slate-200 font-medium transition-colors cursor-pointer"
          >
            监测全网
          </button>
          <button
            onClick={clearAll}
            className="text-xs px-2 py-1 hover:bg-red-50 text-slate-600 hover:text-red-600 rounded border border-slate-200 hover:border-red-100 font-medium transition-colors cursor-pointer"
          >
            清空过滤
          </button>
        </div>
      </div>

      {/* Grid of site categories */}
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 bg-slate-50/25">
        {categories.map((cat) => {
          const isSelected = selectedCategories.includes(cat);
          const sitesInCat = TARGET_SITES.filter(s => s.category === cat);

          return (
            <div
              key={cat}
              onClick={() => toggleCategory(cat)}
              className={`border p-3 rounded-lg transition-all cursor-pointer flex flex-col justify-between group ${
                isSelected
                  ? 'bg-slate-50 border-slate-800 ring-1 ring-slate-800 shadow-xs'
                  : 'bg-white hover:bg-slate-50/55 border-slate-200'
              }`}
            >
              {/* Category Header */}
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className={`p-1.5 rounded-md ${isSelected ? 'bg-slate-200' : 'bg-slate-100 group-hover:bg-slate-200'}`}>
                    {getCategoryIcon(cat)}
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-slate-800">{CATEGORY_NAMES[cat]}</h3>
                    <p className="text-[10px] text-slate-400 font-medium">
                      包含 {sitesInCat.length} 个监测站点
                    </p>
                  </div>
                </div>

                {/* Checkbox */}
                <div className="text-slate-400 group-hover:text-slate-600">
                  {isSelected ? (
                    <CheckSquare className="w-4 h-4 text-slate-800" />
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                </div>
              </div>

              {/* Collapsed Target Site previews */}
              <div className="mt-2.5 border-t border-slate-100/80 pt-2 space-y-1">
                {sitesInCat.slice(0, 2).map(site => (
                  <div key={site.id} className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-500 font-medium truncate max-w-[140px]" title={site.name}>
                      • {site.name.split(' (')[0]}
                    </span>
                    <span className="font-mono text-[9px] text-slate-400 bg-slate-100 px-1 py-0.2 rounded">
                      {site.queryDomain}
                    </span>
                  </div>
                ))}
                {sitesInCat.length > 2 && (
                  <p className="text-[9px] text-slate-400 italic pl-1">
                    以及其它 {sitesInCat.length - 2} 个重点监管域
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Border monitoring active status bar */}
      <div className="px-4 py-2 bg-slate-50 border-t border-slate-150 text-[10px] text-slate-500 flex flex-wrap justify-between items-center gap-2">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="font-medium text-slate-600">情报监听雷达运行中</span>
        </div>
        <span className="text-slate-400">已接入：蒙古边防 (BPO) / 蒙古海关 (GAALI) / 国际刑警 / 中国公安部及二连浩特内蒙协同渠道</span>
      </div>
    </div>
  );
}
