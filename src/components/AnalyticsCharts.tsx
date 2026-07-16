/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useMemo } from 'react';
import { NewsArticle } from '../types';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  CartesianGrid,
  Legend
} from 'recharts';
import { TrendingUp, ShieldAlert, BarChart3, PieChartIcon } from 'lucide-react';

interface AnalyticsChartsProps {
  articles: NewsArticle[];
}

// Elegant, professional, high-contrast palette
const COLORS = [
  '#1e293b', // slate-800 (安纳咖 / 传统毒品)
  '#4f46e5', // indigo-600 (合成毒品)
  '#059669', // emerald-600 (大麻全系)
  '#d97706', // amber-600 (芬太尼)
  '#2563eb', // blue-600 (精神管制)
  '#dc2626', // red-600 (易制毒化学品)
  '#7c3aed', // violet-600 (致幻剂)
  '#64748b'  // slate-500 (其他)
];

export default function AnalyticsCharts({ articles }: AnalyticsChartsProps) {
  
  // 1. Calculate Drug Category distribution
  const categoryData = useMemo(() => {
    const counts: { [key: string]: number } = {};
    articles.forEach(art => {
      const cat = art.category.split(' (')[0]; // Clean label
      counts[cat] = (counts[cat] || 0) + 1;
    });

    return Object.keys(counts).map(name => ({
      name,
      value: counts[name]
    })).sort((a, b) => b.value - a.value);
  }, [articles]);

  // 2. Calculate Risk Level distribution
  const riskStats = useMemo(() => {
    let high = 0, medium = 0, low = 0;
    articles.forEach(art => {
      if (art.riskLevel === 'High') high++;
      else if (art.riskLevel === 'Medium') medium++;
      else low++;
    });

    return { High: high, Medium: medium, Low: low };
  }, [articles]);

  // 3. Hotspots by target sites
  const siteData = useMemo(() => {
    const counts: { [key: string]: number } = {};
    articles.forEach(art => {
      counts[art.siteName] = (counts[art.siteName] || 0) + 1;
    });

    return Object.keys(counts).map(name => ({
      name: name.length > 8 ? name.substring(0, 8) + '...' : name,
      fullFieldName: name,
      count: counts[name]
    })).sort((a, b) => b.count - a.count).slice(0, 5);
  }, [articles]);

  // 4. Trend over the past month (or grouped by days)
  const trendData = useMemo(() => {
    const dateCounts: { [key: string]: number } = {};
    
    // Fill in last 12 days to ensure a smooth timeline even if data is sparse
    const daysToGenerate = 12;
    for (let i = daysToGenerate - 1; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().split('T')[0];
      dateCounts[dateStr] = 0;
    }

    articles.forEach(art => {
      const dateStr = art.date;
      if (dateCounts[dateStr] !== undefined) {
        dateCounts[dateStr]++;
      } else {
        // Only count if it fits within reasonable range
        dateCounts[dateStr] = 1;
      }
    });

    return Object.keys(dateCounts).map(date => {
      // Format to readable MM-DD
      const parts = date.split('-');
      const formattedDate = parts.length === 3 ? `${parts[1]}-${parts[2]}` : date;
      return {
        date: formattedDate,
        '舆情热度 (Intelligence Volume)': dateCounts[date]
      };
    }).sort((a, b) => a.date.localeCompare(b.date));
  }, [articles]);

  if (articles.length === 0) {
    return (
      <div className="bg-white border border-slate-150 p-6 rounded-xl text-center text-slate-400">
        没有足够的情报数据进行多维研判分析。请先进行信源扫描。
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" id="analytics-charts-grid">
      
      {/* 1. Risk Level Quick Stats */}
      <div className="lg:col-span-12 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-white border border-slate-150 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">高危核心警报 (High Threat)</p>
            <h3 className="text-2xl font-bold text-red-600 mt-1">{riskStats.High} <span className="text-xs font-normal text-slate-400">起案件</span></h3>
            <p className="text-[10px] text-slate-400 mt-1">涉及大额走私、跨境团伙或口岸查获</p>
          </div>
          <div className="p-3 bg-red-50 text-red-600 rounded-lg">
            <ShieldAlert className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white border border-slate-150 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">中危研判通报 (Medium Threat)</p>
            <h3 className="text-2xl font-bold text-amber-600 mt-1">{riskStats.Medium} <span className="text-xs font-normal text-slate-400">起事件</span></h3>
            <p className="text-[10px] text-slate-400 mt-1">涉及法规草案、局部案件或行业趋势</p>
          </div>
          <div className="p-3 bg-amber-50 text-amber-600 rounded-lg">
            <BarChart3 className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white border border-slate-150 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">低危公共宣贯 (Low Threat)</p>
            <h3 className="text-2xl font-bold text-slate-700 mt-1">{riskStats.Low} <span className="text-xs font-normal text-slate-400">起报道</span></h3>
            <p className="text-[10px] text-slate-400 mt-1">校园禁毒活动、康复政策与研讨会议</p>
          </div>
          <div className="p-3 bg-slate-100 text-slate-600 rounded-lg">
            <TrendingUp className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* 2. Monthly Trend Chart */}
      <div className="lg:col-span-8 bg-white border border-slate-150 rounded-xl p-4 shadow-xs flex flex-col justify-between min-h-[300px]">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
          <span className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
            <TrendingUp className="w-4 h-4 text-slate-600" /> 近期涉毒舆情热度趋势 (Temporal Trend)
          </span>
          <span className="text-[10px] text-slate-400 font-medium">按监测日期分布统计</span>
        </div>
        <div className="h-[220px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trendData} margin={{ top: 5, right: 10, left: -25, bottom: 0 }}>
              <defs>
                <linearGradient id="colorVolume" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1e293b" stopOpacity={0.2}/>
                  <stop offset="95%" stopColor="#1e293b" stopOpacity={0.0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={10} tickLine={false} />
              <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px', fontSize: '11px' }}
                labelStyle={{ fontWeight: 'bold', color: '#1e293b' }}
              />
              <Area type="monotone" dataKey="舆情热度 (Intelligence Volume)" stroke="#1e293b" strokeWidth={2} fillOpacity={1} fill="url(#colorVolume)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 3. Drug Category Pie Chart */}
      <div className="lg:col-span-4 bg-white border border-slate-150 rounded-xl p-4 shadow-xs flex flex-col justify-between min-h-[300px]">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
          <span className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
            <PieChartIcon className="w-4 h-4 text-slate-600" /> 毒品及管制化学品分类比例
          </span>
        </div>
        
        {categoryData.length > 0 ? (
          <div className="flex flex-col items-center justify-center flex-1">
            <div className="h-[140px] w-[140px] relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={65}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`${value} 篇报道`, '数量']} />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-xs text-slate-400 font-medium">总计</span>
                <span className="text-lg font-bold text-slate-800">{articles.length} 篇</span>
              </div>
            </div>

            {/* Micro-legends */}
            <div className="w-full mt-3 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] font-medium text-slate-600 max-h-[80px] overflow-y-auto">
              {categoryData.slice(0, 6).map((item, index) => (
                <div key={item.name} className="flex items-center gap-1.5 truncate">
                  <span className="w-2.5 h-2.5 rounded-xs shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }}></span>
                  <span className="truncate">{item.name}: {item.value} 篇</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center flex-1 text-slate-400 text-xs">
            暂无类别比例数据
          </div>
        )}
      </div>

      {/* 4. Hotspot monitored sources */}
      <div className="lg:col-span-12 bg-white border border-slate-150 rounded-xl p-4 shadow-xs">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
          <span className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-slate-600" /> 监测情报源发布频度排名前 5 (Source Activity)
          </span>
          <span className="text-[10px] text-slate-400 font-medium">通报发布频度排行</span>
        </div>
        
        {siteData.length > 0 ? (
          <div className="space-y-3">
            {siteData.map((item, index) => {
              const maxCount = siteData[0]?.count || 1;
              const percentage = (item.count / maxCount) * 100;

              return (
                <div key={item.fullFieldName} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-semibold text-slate-700">{index + 1}. {item.fullFieldName}</span>
                    <span className="font-mono text-slate-500 font-medium">{item.count} 篇通报</span>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                    <div 
                      className="bg-slate-700 h-full rounded-full transition-all duration-500"
                      style={{ width: `${percentage}%` }}
                    ></div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-6 text-slate-400 text-xs">
            暂无情报源排行数据
          </div>
        )}
      </div>

    </div>
  );
}
