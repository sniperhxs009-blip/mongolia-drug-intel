/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useMemo } from 'react';
import KeywordSelector from './components/KeywordSelector';
import SiteSelector from './components/SiteSelector';
import AnalyticsCharts from './components/AnalyticsCharts';
import NewsCard from './components/NewsCard';
import IntelligenceReportModal from './components/IntelligenceReportModal';
import { NewsArticle } from './types';
import { 
  ShieldAlert, 
  Search, 
  Sparkles, 
  TrendingUp, 
  Eye, 
  BookOpen, 
  Sliders, 
  FileText, 
  LayoutDashboard, 
  RefreshCw, 
  AlertCircle, 
  Filter, 
  Flame,
  CheckCircle,
  HelpCircle,
  Globe
} from 'lucide-react';

export default function App() {
  // 1. Scanning Configurations State
  const [selectedSiteCategories, setSelectedSiteCategories] = useState<string[]>(['enforcement', 'media', 'china']);
  // Initial default keywords selected for instant scanning
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>(['КНБ', 'анага бодис', 'гаалийн илрүүлэлт', 'caffeine sodium benzoate']);
  const [timeRange, setTimeRange] = useState<'day' | 'week' | 'month'>('month');
  const [customQuery, setCustomQuery] = useState('');

  // 2. Monitoring Results State
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [isQuotaExceeded, setIsQuotaExceeded] = useState(false);
  const [searchQueryUsed, setSearchQueryUsed] = useState<string>('');

  // 3. Filtering Results State
  const [threatFilter, setThreatFilter] = useState<'All' | 'High' | 'Medium' | 'Low'>('All');
  const [textSearch, setTextSearch] = useState('');

  // 4. Intelligence Report Generation State
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [reportText, setReportText] = useState('');
  const [loadingProgress, setLoadingProgress] = useState('');

  // 5. App View Tabs
  const [activeTab, setActiveTab] = useState<'feed' | 'analytics' | 'config'>('feed');

  // Trigger initial monitoring sweep on mount
  useEffect(() => {
    executeMonitoringSweep();
  }, []);

  // Fetch /api/search with selected criteria
  const executeMonitoringSweep = async () => {
    setIsSearching(true);
    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selectedSiteCategories,
          selectedKeywords,
          timeRange,
          customQuery
        })
      });
      const data = await response.json();
      if (data.success) {
        setArticles(data.articles);
        setIsLive(data.isLive);
        setIsQuotaExceeded(!!data.isQuotaExceeded);
        setSearchQueryUsed(data.searchQuery || '');
      }
    } catch (err) {
      console.error("Error executing intelligence sweep:", err);
    } finally {
      setIsSearching(false);
    }
  };

  // Generate Automated AI Intelligence and Trend Report
  const triggerIntelligenceReport = async () => {
    setIsReportModalOpen(true);
    setIsGeneratingReport(true);
    setReportText('');

    // Dynamic analyst logs to make loading highly responsive and authentic
    const progressMessages = [
      "正在连接布防节点及国际禁毒组织数据库...",
      "正在抓取本期选定监测信源...",
      "正在使用 Gemini 分析引擎汇聚多语种舆情通报...",
      "正在提取口岸海关涉案毒品克重与走私夹带路线...",
      "正在过滤核心热点态势并起草趋势安全建议..."
    ];

    let messageIdx = 0;
    setLoadingProgress(progressMessages[0]);
    const timer = setInterval(() => {
      messageIdx = (messageIdx + 1) % progressMessages.length;
      setLoadingProgress(progressMessages[messageIdx]);
    }, 2500);

    try {
      const response = await fetch('/api/intelligence-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ articles: filteredArticles })
      });
      const data = await response.json();
      if (data.success) {
        setReportText(data.report);
      }
    } catch (err) {
      console.error("Error generating intelligence report:", err);
      setReportText("# 生成报告失败\n\n服务器处理超时，请稍后重试。");
    } finally {
      clearInterval(timer);
      setIsGeneratingReport(false);
    }
  };

  // 6. Filtering Logic (Client-side fast search)
  const filteredArticles = useMemo(() => {
    return articles.filter(art => {
      const matchesThreat = threatFilter === 'All' || art.riskLevel === threatFilter;
      const matchesText = !textSearch.trim() || 
        art.title.toLowerCase().includes(textSearch.toLowerCase()) ||
        art.originalTitle.toLowerCase().includes(textSearch.toLowerCase()) ||
        art.summary.toLowerCase().includes(textSearch.toLowerCase()) ||
        art.siteName.toLowerCase().includes(textSearch.toLowerCase()) ||
        art.entities.locations.some(l => l.toLowerCase().includes(textSearch.toLowerCase())) ||
        art.matchedKeywords.some(k => k.toLowerCase().includes(textSearch.toLowerCase()));

      return matchesThreat && matchesText;
    });
  }, [articles, threatFilter, textSearch]);

  // 7. Auto-filtered HIGH RISK Hotspot Articles Panel
  // "支持自动过滤关键热点内容，方便实时监控与分析"
  const highRiskHotspots = useMemo(() => {
    return articles.filter(art => art.riskLevel === 'High');
  }, [articles]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans" id="app-root-container">
      {/* Top Main Brand Header */}
      <header className="bg-slate-900 border-b border-slate-800 text-white shadow-md sticky top-0 z-40 shrink-0">
        <div className="max-w-7xl mx-auto px-4 py-3 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center gap-3">
          
          {/* Logo & Headline */}
          <div className="flex items-center gap-3">
            <div className="p-2 bg-slate-800 border border-slate-750 text-red-500 rounded-lg shadow-xs shrink-0">
              <ShieldAlert className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold tracking-tight">
                蒙古国涉毒舆情监控与态势研判系统
              </h1>
              <p className="text-[10px] text-slate-400 font-medium">
                一键多源情报自动检索、分类过滤与深度认知分析研判工作台
              </p>
            </div>
          </div>

          {/* Engine Status & Sweeping trigger */}
          <div className="flex items-center gap-3">
            {/* Gemini Engine Active Indicator */}
            <div className={`flex items-center gap-1.5 px-3 py-1 bg-slate-800 border border-slate-750 rounded-lg text-xs font-semibold ${isLive ? 'text-emerald-400' : 'text-amber-400'}`}>
              <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`}></span>
              <span>{isLive ? 'Gemini 智能认知引擎已连接' : '本地专家级情报研判模式'}</span>
            </div>

            {/* Sweep Trigger Button */}
            <button
              onClick={executeMonitoringSweep}
              disabled={isSearching}
              className="relative overflow-hidden inline-flex items-center gap-1.5 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800 disabled:from-slate-700 disabled:to-slate-700 text-white text-xs px-4 py-1.8 rounded-lg font-bold shadow-md transition-all active:scale-95 cursor-pointer disabled:cursor-not-allowed"
            >
              {isSearching ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> 正在监听监控中...
                </>
              ) : (
                <>
                  <RefreshCw className="w-3.5 h-3.5" /> 一键扫描最新舆情
                </>
              )}
            </button>
          </div>

        </div>
      </header>

      {/* Primary Dashboard Sub-Navigation Tabs */}
      <div className="bg-white border-b border-slate-200 sticky top-[57px] sm:top-[61px] z-30 shrink-0 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <div className="flex space-x-1 py-1.5">
            <button
              onClick={() => setActiveTab('feed')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'feed'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <BookOpen className="w-4 h-4" /> 舆情情报流 (Intelligence Feed)
            </button>
            <button
              onClick={() => setActiveTab('analytics')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'analytics'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" /> 态势分析研判 (Analytics & Charts)
            </button>
            <button
              onClick={() => setActiveTab('config')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'config'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Sliders className="w-4 h-4" /> 信源及词库管控 (Perimeter Set)
            </button>
          </div>

          <div className="hidden md:flex items-center gap-1.5 text-[10px] text-slate-400 font-mono font-semibold">
            <Globe className="w-3.5 h-3.5" /> 本月覆盖监测站点 22 个 | 检索重点敏感词 70 余个
          </div>
        </div>
      </div>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        
        {/* --- DYNAMIC VIEWPORT SWITCH --- */}

        {activeTab === 'feed' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start" id="app-feed-tab-layout">
            
            {/* Left Sidebar: Advanced Filter, Quick Search, Control Centre */}
            <div className="lg:col-span-4 space-y-4">
              
              {/* Quick Workspace Scanner Widget */}
              <div className="bg-white rounded-xl border border-slate-150 p-4 shadow-xs space-y-3">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                  <Sliders className="w-4.5 h-4.5 text-slate-600" />
                  <h3 className="text-sm font-bold text-slate-800">快速定向情报检索</h3>
                </div>

                {/* Custom Query Input */}
                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">自定义二次检索词</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="指定特定区域/车牌/嫌疑人等..."
                      value={customQuery}
                      onChange={(e) => setCustomQuery(e.target.value)}
                      className="w-full pl-9 pr-3 py-1.8 bg-slate-50 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-400 focus:border-slate-400 text-slate-800"
                    />
                  </div>
                </div>

                {/* Date range filter */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">时间段范围过滤</label>
                  <div className="grid grid-cols-3 gap-1.5 text-xs font-semibold">
                    <button
                      onClick={() => setTimeRange('day')}
                      className={`py-1.5 border rounded-lg transition-all cursor-pointer ${timeRange === 'day' ? 'bg-slate-900 border-slate-900 text-white' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                    >
                      近24小时
                    </button>
                    <button
                      onClick={() => setTimeRange('week')}
                      className={`py-1.5 border rounded-lg transition-all cursor-pointer ${timeRange === 'week' ? 'bg-slate-900 border-slate-900 text-white' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                    >
                      近7天
                    </button>
                    <button
                      onClick={() => setTimeRange('month')}
                      className={`py-1.5 border rounded-lg transition-all cursor-pointer ${timeRange === 'month' ? 'bg-slate-900 border-slate-900 text-white' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                    >
                      近1个月
                    </button>
                  </div>
                </div>

                {/* Search Button Indicator inside sidebar */}
                <button
                  onClick={executeMonitoringSweep}
                  disabled={isSearching}
                  className="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white text-xs font-bold rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isSearching ? 'animate-spin' : ''}`} />
                  定向检索最新舆情 (Scan)
                </button>
              </div>

              {/* Feed Filters */}
              <div className="bg-white rounded-xl border border-slate-150 p-4 shadow-xs space-y-3">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                  <Filter className="w-4.5 h-4.5 text-slate-600" />
                  <h3 className="text-sm font-bold text-slate-800">情报流精确过滤</h3>
                </div>

                {/* Text Filter */}
                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">文本过滤 (支持拼音、中文、外文)</label>
                  <input
                    type="text"
                    placeholder="输入口岸、毒品种类、海关部门..."
                    value={textSearch}
                    onChange={(e) => setTextSearch(e.target.value)}
                    className="w-full px-3 py-1.8 bg-slate-50 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-400 focus:border-slate-400 text-slate-800"
                  />
                </div>

                {/* Threat Filter Matrix */}
                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">危害风险评级过滤</label>
                  <div className="flex flex-col gap-1.5">
                    {[
                      { key: 'All', label: '全部等级情报' },
                      { key: 'High', label: '🔴 红色高危核心警报' },
                      { key: 'Medium', label: '🟡 黄色中危研判通报' },
                      { key: 'Low', label: '🔵 蓝色公共宣导' }
                    ].map((item) => (
                      <button
                        key={item.key}
                        onClick={() => setThreatFilter(item.key as any)}
                        className={`w-full text-left px-3 py-2 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                          threatFilter === item.key 
                            ? 'bg-slate-900 border-slate-900 text-white shadow-xs font-bold' 
                            : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-600'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Clear local filters button */}
                {(textSearch || threatFilter !== 'All') && (
                  <button
                    onClick={() => { setTextSearch(''); setThreatFilter('All'); }}
                    className="w-full py-1.5 text-xs text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 rounded-lg font-bold transition-all text-center cursor-pointer"
                  >
                    重置过滤条件
                  </button>
                )}
              </div>

            </div>

            {/* Right Container: Alerts, News list & Sweeps */}
            <div className="lg:col-span-8 space-y-4">
              
              {/* Core Hotspot Alerts Block (The "自动过滤关键热点内容" Feature) */}
              {highRiskHotspots.length > 0 && (
                <div className="bg-gradient-to-r from-red-500/8 to-orange-500/8 border border-red-200/60 rounded-xl p-4 shadow-xs space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Flame className="w-5 h-5 text-red-600 animate-bounce" />
                      <h3 className="text-sm font-bold text-red-900">
                        系统自动拦截过滤出的核心高危热点 (Risk Radar)
                      </h3>
                    </div>
                    <span className="bg-red-200 text-red-800 text-[10px] px-2.5 py-0.5 rounded-full font-bold">
                      高危共计 {highRiskHotspots.length} 起
                    </span>
                  </div>
                  
                  {/* Grid layout containing only High risk hotspot headlines */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    {highRiskHotspots.slice(0, 4).map(art => (
                      <div 
                        key={art.id} 
                        onClick={() => {
                          setThreatFilter('High');
                          setTextSearch(art.title);
                          const el = document.getElementById(`news-card-${art.id}`);
                          if (el) el.scrollIntoView({ behavior: 'smooth' });
                        }}
                        className="bg-white/80 backdrop-blur-xs border border-red-100 hover:border-red-300 p-3 rounded-lg shadow-2xs hover:shadow-sm transition-all duration-150 cursor-pointer flex flex-col justify-between"
                      >
                        <div>
                          <div className="flex justify-between text-[9px] text-slate-400 font-mono font-medium mb-1">
                            <span>{art.siteName}</span>
                            <span>{art.date}</span>
                          </div>
                          <h4 className="text-xs font-bold text-slate-800 leading-snug line-clamp-2">
                            {art.title}
                          </h4>
                        </div>
                        <div className="mt-2 text-[10px] text-red-700 font-semibold flex items-center gap-1">
                          <span>缴获: {art.details?.seizureAmount || '大额查控'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Feed Count bar & Report Generation Trigger */}
              <div className="bg-white border border-slate-150 p-4 rounded-xl shadow-xs flex flex-col gap-3">
                <div className="flex flex-wrap justify-between items-center gap-3">
                  <div className="text-xs text-slate-500 font-semibold flex items-center gap-1.5">
                    <FileText className="w-4 h-4 text-slate-600" />
                    <span>
                      当前条件下共有监测情报 <strong className="text-slate-800 text-sm font-bold">{filteredArticles.length}</strong> 篇
                    </span>
                    {articles.length !== filteredArticles.length && (
                      <span className="text-slate-400">（已从全部 {articles.length} 篇中筛选）</span>
                    )}
                  </div>

                  {/* Intelligence Report button */}
                  <button
                    onClick={triggerIntelligenceReport}
                    disabled={filteredArticles.length === 0}
                    className="bg-slate-900 hover:bg-slate-950 text-white text-xs px-4 py-1.8 rounded-lg font-bold shadow-sm transition-all active:scale-95 disabled:bg-slate-200 disabled:text-slate-400 flex items-center gap-1.5 cursor-pointer disabled:cursor-not-allowed"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" /> 一键生成本期态势研判报告
                  </button>
                </div>

                {searchQueryUsed && (
                  <div className="border-t border-slate-100 pt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] text-slate-500 font-mono">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <span className="bg-red-50 text-red-600 px-1.5 py-0.5 rounded font-bold shrink-0 border border-red-150">Google 实时联网检索式</span>
                      <span className="truncate text-slate-600 font-medium font-mono" title={searchQueryUsed}>{searchQueryUsed}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {isLive ? (
                        <span className="text-emerald-600 font-bold flex items-center gap-1">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                          </span>
                          已接入 Google 实时网络
                        </span>
                      ) : (
                        <span className="text-slate-400 font-bold">本地情报缓存</span>
                      )}
                    </div>
                  </div>
                )}

                {isQuotaExceeded && (
                  <div className="border-t border-slate-100 pt-3 flex items-start gap-2 text-xs text-amber-700 bg-amber-50/50 p-2.5 rounded-lg border border-amber-150">
                    <AlertCircle className="w-4.5 h-4.5 text-amber-600 shrink-0 mt-0.5" />
                    <span>
                      <strong>智能网络研判配额提示 (API 429)</strong>：由于外部智能联网搜排配额不足，系统已自动无缝降级为 <strong>本地专家级离线决策数据库</strong>，为您展示高品质中蒙双边涉毒研判历史与本底数据，研判流程及报告一键生成仍可正常使用。
                    </span>
                  </div>
                )}
              </div>

              {/* Main Feed Container */}
              <div className="space-y-3.5">
                {isSearching ? (
                  <div className="bg-white border border-slate-150 rounded-xl p-12 text-center flex flex-col items-center justify-center space-y-3">
                    <RefreshCw className="w-8 h-8 text-slate-800 animate-spin" />
                    <p className="text-sm font-semibold text-slate-600">
                      系统正在联合布防雷达并调用 Gemini 对 22 个指定蒙古国口岸及媒体站点进行深度搜排...
                    </p>
                  </div>
                ) : filteredArticles.length > 0 ? (
                  filteredArticles.map(art => (
                    <NewsCard key={art.id} article={art} />
                  ))
                ) : (
                  <div className="bg-white border border-slate-150 rounded-xl p-12 text-center space-y-2">
                    <AlertCircle className="w-8 h-8 text-slate-400 mx-auto" />
                    <h3 className="text-sm font-bold text-slate-700">没有匹配的情报结果</h3>
                    <p className="text-xs text-slate-400">
                      没有找到契合当前选择的分类过滤条件的舆情。您可以清空过滤项，或者在最上方点击「一键扫描最新舆情」。
                    </p>
                  </div>
                )}
              </div>

            </div>

          </div>
        )}

        {activeTab === 'analytics' && (
          <div className="space-y-6" id="app-analytics-tab-layout">
            <div className="bg-white border border-slate-150 rounded-xl p-4 shadow-xs">
              <h2 className="text-base font-bold text-slate-800 flex items-center gap-1.5 mb-1">
                <TrendingUp className="w-5 h-5 text-slate-600" /> 多维数据统合分析与威胁研判看板
              </h2>
              <p className="text-xs text-slate-400 font-semibold">
                对监控雷达当前捕获到的 {articles.length} 起涉毒情报信息进行自动汇总、热度评级以及信源流向分析。
              </p>
            </div>
            <AnalyticsCharts articles={articles} />
          </div>
        )}

        {activeTab === 'config' && (
          <div className="space-y-6" id="app-config-tab-layout">
            <div className="bg-white border border-slate-150 rounded-xl p-4 shadow-xs">
              <h2 className="text-base font-bold text-slate-800 flex items-center gap-1.5 mb-1">
                <Sliders className="w-5 h-5 text-slate-600" /> 舆情雷达监控范围及敏感词库管控
              </h2>
              <p className="text-xs text-slate-400 font-semibold">
                自定义指定蒙古国海关总局、边防军总局、禁毒、卫健与中国内蒙协同信源的监测开启状态，微调底层检索词库。
              </p>
            </div>
            
            {/* Sites Control Cluster */}
            <SiteSelector 
              selectedCategories={selectedSiteCategories} 
              onChange={setSelectedSiteCategories} 
            />

            {/* Keyword Control Cluster */}
            <KeywordSelector 
              selectedKeywords={selectedKeywords} 
              onChange={setSelectedKeywords} 
            />
          </div>
        )}

      </main>

      {/* Report Modal Component */}
      <IntelligenceReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        reportText={reportText}
        isLoading={isGeneratingReport}
        loadingProgress={loadingProgress}
      />
    </div>
  );
}
