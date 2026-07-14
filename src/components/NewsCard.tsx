/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { NewsArticle } from '../types';
import { 
  Calendar, 
  MapPin, 
  Building, 
  User, 
  ChevronDown, 
  ChevronUp, 
  ExternalLink, 
  Copy, 
  Check,
  AlertTriangle,
  FileText,
  BadgeAlert,
  ArrowRightLeft
} from 'lucide-react';

interface NewsCardProps {
  article: NewsArticle;
}

export default function NewsCard({ article }: NewsCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyOriginalTitle = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(article.originalTitle);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Assign classes based on threat assessment level
  const getRiskStyles = (risk: 'High' | 'Medium' | 'Low') => {
    switch (risk) {
      case 'High':
        return {
          bg: 'bg-red-50 border-red-200',
          text: 'text-red-800',
          badge: 'bg-red-600 text-white border-red-600',
          accent: 'border-l-4 border-l-red-600'
        };
      case 'Medium':
        return {
          bg: 'bg-amber-50 border-amber-200',
          text: 'text-amber-800',
          badge: 'bg-amber-500 text-white border-amber-500',
          accent: 'border-l-4 border-l-amber-500'
        };
      case 'Low':
        return {
          bg: 'bg-slate-50 border-slate-200',
          text: 'text-slate-700',
          badge: 'bg-slate-500 text-white border-slate-500',
          accent: 'border-l-4 border-l-slate-400'
        };
    }
  };

  const threatStyles = getRiskStyles(article.riskLevel);

  return (
    <div 
      className={`bg-white border rounded-xl overflow-hidden shadow-xs hover:shadow-md transition-all duration-200 cursor-pointer ${threatStyles.accent} border-slate-150`}
      onClick={() => setIsExpanded(!isExpanded)}
      id={`news-card-${article.id}`}
    >
      {/* Top Header Row (Always visible) */}
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap justify-between items-center gap-2 mb-2.5">
          {/* Metadata Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {/* Risk Level Badge */}
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 ${threatStyles.badge}`}>
              <AlertTriangle className="w-3 h-3 shrink-0" />
              {article.riskLevel === 'High' ? '红色高危核心警报' : article.riskLevel === 'Medium' ? '黄色中危研判通报' : '蓝色公共宣导'}
            </span>

            {/* Source Website Friendly Badge */}
            <span className="bg-slate-100 text-slate-800 border border-slate-200 px-2.5 py-0.5 rounded-full text-[10px] font-semibold">
              {article.siteName}
            </span>

            {/* Drug Type Badge */}
            <span className="bg-slate-800 text-slate-100 px-2.5 py-0.5 rounded-full text-[10px] font-medium font-mono">
              {article.category}
            </span>
          </div>

          {/* Publication Date */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono font-medium">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            {article.date}
          </div>
        </div>

        {/* Headlines */}
        <div className="space-y-1.5">
          <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight leading-snug">
            {article.title}
          </h3>

          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
            <span className="shrink-0 font-medium text-slate-400">[原文]</span>
            <span className="truncate italic flex-1">{article.originalTitle}</span>
            <button
              onClick={copyOriginalTitle}
              className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-700 transition-colors shrink-0"
              title="复制原文标题"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Chinese Core Analytical Summary (Short snippet) */}
        <p className="mt-3 text-xs sm:text-sm text-slate-600 leading-relaxed font-medium">
          {article.summary.length > 180 ? `${article.summary.substring(0, 180)}...` : article.summary}
        </p>

        {/* Brief Entity Badges for fast scanning */}
        <div className="mt-3.5 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {article.entities.locations.length > 0 && (
              <span className="flex items-center gap-1 font-medium">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-700">{article.entities.locations[0]}</span>
                {article.entities.locations.length > 1 && (
                  <span className="text-[10px] bg-slate-100 text-slate-500 px-1 rounded">+{article.entities.locations.length - 1}</span>
                )}
              </span>
            )}

            {article.entities.organizations.length > 0 && (
              <span className="flex items-center gap-1 font-medium">
                <Building className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-700">{article.entities.organizations[0]}</span>
              </span>
            )}

            {article.entities.suspects && (
              <span className="flex items-center gap-1 font-medium">
                <User className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-700 truncate max-w-[120px]">{article.entities.suspects}</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* 查看原文 Button */}
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-xs font-bold text-blue-700 hover:text-blue-900 flex items-center gap-1 transition-all border border-blue-200 hover:border-blue-300 bg-blue-50/70 hover:bg-blue-50 px-2.5 py-1 rounded-lg cursor-pointer"
            >
              查看原文 <ExternalLink className="w-3.5 h-3.5 text-blue-600" />
            </a>

            {/* Toggle Expand trigger button */}
            <button className="text-xs font-semibold text-slate-800 hover:text-slate-900 flex items-center gap-1 transition-colors cursor-pointer">
              {isExpanded ? (
                <>收起研判报告 <ChevronUp className="w-4 h-4" /></>
              ) : (
                <>展开深度研判 <ChevronDown className="w-4 h-4" /></>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded Intelligence Body */}
      {isExpanded && (
        <div className="px-4 pb-5 sm:px-5 sm:pb-6 pt-1 border-t border-slate-100 bg-slate-50/40 space-y-4">
          
          {/* Deep Summary Panel */}
          <div className="space-y-1.5">
            <h4 className="text-xs font-bold text-slate-800 flex items-center gap-1">
              <FileText className="w-4 h-4 text-slate-600" /> 中文情报研判概要 (Intelligence Brief)
            </h4>
            <div className="bg-white border border-slate-150 p-3 rounded-lg text-xs sm:text-sm text-slate-700 leading-relaxed shadow-xs">
              {article.summary}
            </div>
          </div>

          {/* Seizure & Route Details */}
          {article.details && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Quantities seized */}
              <div className="bg-white border border-slate-150 p-3 rounded-lg space-y-1 shadow-xs">
                <h5 className="text-xs font-bold text-slate-800 flex items-center gap-1">
                  <BadgeAlert className="w-3.5 h-3.5 text-red-600" /> 缴获物品/毒品数量
                </h5>
                <p className="text-xs text-slate-600 font-medium">
                  {article.details.seizureAmount || '未列明具体缴获数额'}
                </p>
              </div>

              {/* Transit Route */}
              <div className="bg-white border border-slate-150 p-3 rounded-lg space-y-1 shadow-xs">
                <h5 className="text-xs font-bold text-slate-800 flex items-center gap-1">
                  <ArrowRightLeft className="w-3.5 h-3.5 text-slate-600" /> 运输/夹带路线
                </h5>
                <p className="text-xs text-slate-600 font-medium">
                  {article.details.traffickingRoute || '不适用/不详'}
                </p>
              </div>

              {/* Law enforcement sentences/actions */}
              <div className="bg-white border border-slate-150 p-3 rounded-lg space-y-1 md:col-span-2 shadow-xs">
                <h5 className="text-xs font-bold text-slate-800 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5 text-slate-600" /> 执法处置与处罚法条
                </h5>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {article.details.penalties || '不详/正在审理中'}
                </p>
              </div>
            </div>
          )}

          {/* Full Entities List */}
          <div className="bg-white border border-slate-150 p-3 rounded-lg space-y-2 shadow-xs">
            <h5 className="text-xs font-bold text-slate-800">情报涉及的核心实体要素</h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div className="flex items-start gap-1">
                <span className="text-slate-400 font-medium w-16">涉案地域:</span>
                <span className="text-slate-700 font-semibold">{article.entities.locations.join('、') || '未列明'}</span>
              </div>
              <div className="flex items-start gap-1">
                <span className="text-slate-400 font-medium w-16">相关部门:</span>
                <span className="text-slate-700 font-semibold">{article.entities.organizations.join('、') || '未列明'}</span>
              </div>
            </div>
          </div>

          {/* Keywords Highlight */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mr-1">命中敏感词条:</span>
            {article.matchedKeywords.map((kw, idx) => (
              <span key={idx} className="bg-slate-100 hover:bg-slate-200 text-slate-800 text-[10px] font-mono px-2 py-0.5 rounded transition-colors font-medium">
                {kw}
              </span>
            ))}
          </div>

          {/* Deep link button */}
          <div className="flex justify-end pt-1">
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 bg-slate-800 hover:bg-slate-900 text-white text-xs px-3.5 py-1.5 rounded-lg transition-colors font-semibold shadow-xs"
            >
              浏览原始通报网面 <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>

        </div>
      )}
    </div>
  );
}
