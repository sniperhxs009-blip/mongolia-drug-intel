/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo } from 'react';
import { DRUG_KEYWORDS, CATEGORY_LABELS } from '../data/keywords';
import { DrugKeyword } from '../types';
import { Search, Tag, Check, Square, CheckSquare, Sparkles, Filter, RefreshCw } from 'lucide-react';

interface KeywordSelectorProps {
  selectedKeywords: string[];
  onChange: (keywords: string[]) => void;
}

export default function KeywordSelector({ selectedKeywords, onChange }: KeywordSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'mn' | 'en' | 'ru'>('all');
  const [activeCategory, setActiveCategory] = useState<string>('all');

  // Group keywords by category for rendering
  const categories = useMemo(() => {
    return Object.keys(CATEGORY_LABELS) as (keyof typeof CATEGORY_LABELS)[];
  }, []);

  const filteredKeywords = useMemo(() => {
    return DRUG_KEYWORDS.filter(kw => {
      const matchesSearch = 
        kw.word.toLowerCase().includes(searchQuery.toLowerCase()) ||
        kw.translation.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesLanguage = activeTab === 'all' || kw.language === activeTab;
      const matchesCategory = activeCategory === 'all' || kw.category === activeCategory;

      return matchesSearch && matchesLanguage && matchesCategory;
    });
  }, [searchQuery, activeTab, activeCategory]);

  const toggleKeyword = (word: string) => {
    if (selectedKeywords.includes(word)) {
      onChange(selectedKeywords.filter(w => w !== word));
    } else {
      onChange([...selectedKeywords, word]);
    }
  };

  const toggleCategoryKeywords = (category: string) => {
    const categoryWords = DRUG_KEYWORDS.filter(kw => kw.category === category).map(kw => kw.word);
    const allSelected = categoryWords.every(w => selectedKeywords.includes(w));

    if (allSelected) {
      // Remove all of this category
      onChange(selectedKeywords.filter(w => !categoryWords.includes(w)));
    } else {
      // Add missing ones
      const newSelection = [...selectedKeywords];
      categoryWords.forEach(w => {
        if (!newSelection.includes(w)) {
          newSelection.push(w);
        }
      });
      onChange(newSelection);
    }
  };

  // Pre-configured intelligence scanning presets
  const applyPreset = (presetType: 'anaga' | 'synthetics' | 'cannabis' | 'all') => {
    switch (presetType) {
      case 'anaga':
        // Select all CNB keywords + action words
        const anagaWords = DRUG_KEYWORDS.filter(kw => kw.category === 'cnb' || kw.category === 'actions').map(kw => kw.word);
        onChange(anagaWords);
        break;
      case 'synthetics':
        // Select amphetamine, fentanyl, cathinone, hallucinogen keywords
        const synthWords = DRUG_KEYWORDS.filter(kw => 
          ['amphetamine', 'fentanyl', 'cathinone', 'hallucinogens', 'psychotropic'].includes(kw.category)
        ).map(kw => kw.word);
        onChange(synthWords);
        break;
      case 'cannabis':
        // Select cannabis and precursors
        const cannabisWords = DRUG_KEYWORDS.filter(kw => kw.category === 'cannabis' || kw.category === 'precursors').map(kw => kw.word);
        onChange(cannabisWords);
        break;
      case 'all':
        // Select everything
        onChange(DRUG_KEYWORDS.map(kw => kw.word));
        break;
      default:
        break;
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-150 shadow-sm overflow-hidden" id="keyword-selector-panel">
      {/* Header */}
      <div className="p-4 bg-gradient-to-r from-slate-50 to-slate-100 border-b border-slate-150 flex flex-wrap justify-between items-center gap-3">
        <div className="flex items-center gap-2">
          <Tag className="w-5 h-5 text-slate-600" />
          <h2 className="text-base font-semibold text-slate-800">
            三语种蒙古国毒品及管制化学品检索词库
          </h2>
          <span className="bg-slate-200 text-slate-700 text-xs px-2.5 py-0.5 rounded-full font-medium">
            已选 {selectedKeywords.length} 个词
          </span>
        </div>

        {/* Tactical scanning presets */}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500 flex items-center gap-1 font-medium">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" /> 智能扫描预设:
          </span>
          <button
            onClick={() => applyPreset('anaga')}
            className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-md font-medium transition-colors cursor-pointer"
          >
            安纳咖专项
          </button>
          <button
            onClick={() => applyPreset('synthetics')}
            className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-800 border border-indigo-200 rounded-md font-medium transition-colors cursor-pointer"
          >
            新型合成毒品
          </button>
          <button
            onClick={() => applyPreset('cannabis')}
            className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 rounded-md font-medium transition-colors cursor-pointer"
          >
            大麻与易制毒
          </button>
          <button
            onClick={() => applyPreset('all')}
            className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 rounded-md font-medium transition-colors cursor-pointer"
          >
            全量检索
          </button>
          <button
            onClick={() => onChange([])}
            className="px-2.5 py-1 hover:bg-red-50 text-slate-600 hover:text-red-600 border border-slate-200 hover:border-red-200 rounded-md transition-colors cursor-pointer flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> 重置
          </button>
        </div>
      </div>

      {/* Controls & Filters */}
      <div className="p-4 border-b border-slate-150 grid grid-cols-1 md:grid-cols-12 gap-3 bg-slate-50/50">
        {/* Search */}
        <div className="relative md:col-span-4">
          <Search className="absolute left-3 top-2.5 w-4.5 h-4.5 text-slate-400" />
          <input
            type="text"
            placeholder="搜索关键词或中文翻译..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 bg-white text-sm border border-slate-250 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
          />
        </div>

        {/* Language Tabs */}
        <div className="flex bg-slate-100 p-0.5 rounded-lg border border-slate-200 md:col-span-4 text-xs font-medium">
          <button
            onClick={() => setActiveTab('all')}
            className={`flex-1 py-1.5 rounded-md transition-all cursor-pointer ${activeTab === 'all' ? 'bg-white text-slate-800 shadow-xs font-semibold' : 'text-slate-500 hover:text-slate-800'}`}
          >
            全部语言
          </button>
          <button
            onClick={() => setActiveTab('mn')}
            className={`flex-1 py-1.5 rounded-md transition-all cursor-pointer ${activeTab === 'mn' ? 'bg-white text-slate-800 shadow-xs font-semibold' : 'text-slate-500 hover:text-slate-800'}`}
          >
            蒙古文 (MN)
          </button>
          <button
            onClick={() => setActiveTab('en')}
            className={`flex-1 py-1.5 rounded-md transition-all cursor-pointer ${activeTab === 'en' ? 'bg-white text-slate-800 shadow-xs font-semibold' : 'text-slate-500 hover:text-slate-800'}`}
          >
            英文 (EN)
          </button>
          <button
            onClick={() => setActiveTab('ru')}
            className={`flex-1 py-1.5 rounded-md transition-all cursor-pointer ${activeTab === 'ru' ? 'bg-white text-slate-800 shadow-xs font-semibold' : 'text-slate-500 hover:text-slate-800'}`}
          >
            俄文 (RU)
          </button>
        </div>

        {/* Category filter dropdown */}
        <div className="relative md:col-span-4">
          <div className="absolute left-3 top-2.5 text-slate-400">
            <Filter className="w-4 h-4" />
          </div>
          <select
            value={activeCategory}
            onChange={(e) => setActiveCategory(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 bg-white text-sm border border-slate-250 rounded-lg appearance-none focus:outline-none focus:ring-2 focus:ring-slate-500 focus:border-slate-500 cursor-pointer"
          >
            <option value="all">选择分类：全部毒品类别</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {CATEGORY_LABELS[cat]}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Grid of Keywords grouped by category */}
      <div className="p-4 max-h-[380px] overflow-y-auto space-y-4 scrollbar-thin">
        {categories.map((cat) => {
          // Filter keywords for this category
          const catKeywords = filteredKeywords.filter(kw => kw.category === cat);
          if (catKeywords.length === 0) return null;

          const catWords = catKeywords.map(kw => kw.word);
          const isCategoryAllSelected = catWords.every(w => selectedKeywords.includes(w));
          const isCategorySomeSelected = catWords.some(w => selectedKeywords.includes(w)) && !isCategoryAllSelected;

          return (
            <div key={cat} className="border border-slate-100 rounded-lg p-3 bg-slate-50/20">
              {/* Category Subheader */}
              <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2.5">
                <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                  <span className="w-1.5 h-3 bg-slate-600 rounded-sm"></span>
                  {CATEGORY_LABELS[cat]}
                </span>
                
                {/* Category toggle checkbox */}
                <button
                  onClick={() => toggleCategoryKeywords(cat)}
                  className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 cursor-pointer font-medium"
                >
                  {isCategoryAllSelected ? (
                    <CheckSquare className="w-3.5 h-3.5 text-slate-600" />
                  ) : isCategorySomeSelected ? (
                    <div className="w-3.5 h-3.5 bg-slate-200 border border-slate-400 rounded-xs flex items-center justify-center">
                      <div className="w-2 h-0.5 bg-slate-600"></div>
                    </div>
                  ) : (
                    <Square className="w-3.5 h-3.5" />
                  )}
                  全选分类
                </button>
              </div>

              {/* Tag Badges */}
              <div className="flex flex-wrap gap-2">
                {catKeywords.map((kw) => {
                  const isSelected = selectedKeywords.includes(kw.word);
                  return (
                    <button
                      key={kw.id}
                      onClick={() => toggleKeyword(kw.word)}
                      className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-slate-800 text-white border-slate-800 font-medium shadow-xs'
                          : 'bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-900 border-slate-200'
                      }`}
                    >
                      {isSelected ? (
                        <Check className="w-3 h-3 text-slate-200" />
                      ) : (
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          kw.language === 'mn' ? 'bg-sky-400' : kw.language === 'en' ? 'bg-indigo-400' : 'bg-red-400'
                        }`} title={kw.language === 'mn' ? '蒙古文' : kw.language === 'en' ? '英文' : '俄文'}></span>
                      )}
                      
                      <span className="font-mono font-medium">{kw.word}</span>
                      
                      <span className={`text-[10px] font-normal border-l pl-1.5 ${
                        isSelected ? 'text-slate-300 border-slate-700' : 'text-slate-400 border-slate-150 group-hover:text-slate-500'
                      }`}>
                        {kw.translation}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {filteredKeywords.length === 0 && (
          <div className="text-center py-8 text-slate-400 text-sm">
            没有找到与 “{searchQuery}” 相匹配的管制词条或关键词。
          </div>
        )}
      </div>
      
      {/* Footer statistics */}
      <div className="px-4 py-2 bg-slate-50 border-t border-slate-150 text-[10px] text-slate-500 flex justify-between">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-sky-400"></span> 蓝色: 蒙古文 (标准执法) | 
          <span className="w-2 h-2 rounded-full bg-indigo-400 ml-1"></span> 靛色: 英文 (国际惯用) | 
          <span className="w-2 h-2 rounded-full bg-red-400 ml-1"></span> 红色: 俄文 (俄蒙协同)
        </span>
        <span>当前共加载词条 {DRUG_KEYWORDS.length} 条</span>
      </div>
    </div>
  );
}
