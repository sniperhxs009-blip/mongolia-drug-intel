/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { X, Copy, Check, Download, ShieldAlert, FileSpreadsheet, Loader2 } from 'lucide-react';

interface IntelligenceReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  reportText: string;
  isLoading: boolean;
  loadingProgress: string;
}

export default function IntelligenceReportModal({
  isOpen,
  onClose,
  reportText,
  isLoading,
  loadingProgress
}: IntelligenceReportModalProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(reportText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([reportText], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', '蒙古国涉毒舆情情报监控研判报告.md');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs" id="intelligence-report-modal-overlay">
      <div 
        className="relative bg-white w-full max-w-4xl h-[85vh] rounded-xl border border-slate-200 shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 bg-gradient-to-r from-slate-800 to-slate-950 text-white flex justify-between items-center shrink-0">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-red-400" />
            <div>
              <h3 className="text-base font-bold">蒙古国涉毒情报与态势研判报告</h3>
              <p className="text-[10px] text-slate-300 font-medium">由 Gemini 认知分析引擎综合多维通报实时整合生成</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1 hover:bg-slate-700/50 rounded-lg transition-colors cursor-pointer text-slate-300 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Action Toolbar */}
        {!isLoading && reportText && (
          <div className="px-5 py-2.5 bg-slate-100 border-b border-slate-200 flex justify-between items-center text-xs shrink-0">
            <span className="text-slate-500 font-medium">情报格式: Markdown 格式研判书</span>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-md font-semibold transition-colors cursor-pointer"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" /> 已复制内容
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" /> 复制研判全文
                  </>
                )}
              </button>
              <button
                onClick={handleDownload}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white border border-slate-800 rounded-md font-semibold transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" /> 导出 Markdown
              </button>
            </div>
          </div>
        )}

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
          {isLoading ? (
            <div className="h-full flex flex-col items-center justify-center space-y-4">
              <Loader2 className="w-10 h-10 text-slate-800 animate-spin" />
              <div className="text-center space-y-1">
                <p className="text-sm font-bold text-slate-700">正在生成深度决策情报...</p>
                <p className="text-xs text-slate-400 font-mono">{loadingProgress}</p>
              </div>
            </div>
          ) : reportText ? (
            <div className="markdown-body prose prose-slate max-w-none prose-sm text-slate-800 leading-relaxed font-normal">
              <ReactMarkdown>{reportText}</ReactMarkdown>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 text-sm">
              暂无报告数据
            </div>
          )}
        </div>

        {/* Footer info stamp */}
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-150 text-[10px] text-slate-400 text-center shrink-0">
          声明: 本研判报告完全基于选定信源发布的公开资讯进行自动化关联研判，供打击跨境毒品犯罪与海关监管研判工作参考。
        </div>
      </div>
    </div>
  );
}
