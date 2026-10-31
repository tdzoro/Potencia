import React from 'react'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center items-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-premium p-8 text-center border border-slate-100">
        <div className="w-12 h-12 bg-brand-50 rounded-xl flex items-center justify-center mx-auto mb-4 text-brand-600 font-bold text-2xl">
          IQ
        </div>
        <h1 className="text-2xl font-bold text-slate-900 mb-2">ResumeIQ</h1>
        <p className="text-slate-600 text-sm mb-6">
          AI-Powered Resume Analyzer & ATS Optimization Engine
        </p>
        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-brand-100 text-brand-800">
          Phase 1 Scaffolding Ready
        </span>
      </div>
    </div>
  )
}
