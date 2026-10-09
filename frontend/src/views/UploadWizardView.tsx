import React, { useState, useEffect } from 'react';
import {
  Upload,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  FileCode,
  Sparkles,
  Coins,
  Tag,
  X,
  Plus,
  AlertCircle,
} from 'lucide-react';
import { UserAccount, AppDataset, PageRoute } from '../types';

interface UploadWizardViewProps {
  currentUser: UserAccount;
  onPublishDataset: (newDataset: AppDataset, earnedCredits: number) => void;
  onNavigate: (route: PageRoute) => void;
}

export const UploadWizardView: React.FC<UploadWizardViewProps> = ({
  currentUser,
  onPublishDataset,
  onNavigate,
}) => {
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Step 1: Details
  const [name, setName] = useState('Customer Churn Analysis Q4');
  const [description, setDescription] = useState(
    'Comprehensive behavioral customer churn records with tenure, contract terms, monthly fees, and cancellation flags.'
  );
  const [category, setCategory] = useState<string>('Telecom');
  const [tags, setTags] = useState<string[]>(['churn', 'telecom', 'analytics']);
  const [tagInput, setTagInput] = useState<string>('');
  const [license, setLicense] = useState<string>('MIT');

  // Step 2: File Drop Zone
  const [selectedFile, setSelectedFile] = useState<{ name: string; sizeMb: number; type: 'csv' | 'xlsx' } | null>({
    name: 'customer_churn_q4_telecom.csv',
    sizeMb: 12.4,
    type: 'csv',
  });
  const [fileProgress, setFileProgress] = useState<number>(100);
  const [fileError, setFileError] = useState<string | null>(null);

  // Step 3: Live Evaluation
  const [evalProgress, setEvalProgress] = useState<number>(0);
  const [evalStageIndex, setEvalStageIndex] = useState<number>(0);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [evaluationComplete, setEvaluationComplete] = useState<boolean>(false);

  // Evaluation Scores
  const qualityScore = 85;
  const relevanceScore = 90;
  const overallScore = (qualityScore + relevanceScore) / 2; // 87.5
  // Credit calculation: 50 + floor(85 * 0.3) + floor(90 / 6) = 50 + 25 + 15 = 90
  const earnedCredits = 90;

  // Validation rules for Step 1
  const isNameValid = name.trim().length >= 3 && name.trim().length <= 80;
  const isDescValid = description.trim().length >= 10 && description.trim().length <= 1000;
  const canProceedStep1 = isNameValid && isDescValid;

  const handleAddTag = () => {
    const trimmed = tagInput.trim().toLowerCase().replace(/[^a-z0-9-]/g, '');
    if (!trimmed) return;
    if (tags.length >= 10) return;
    if (!tags.includes(trimmed)) {
      setTags([...tags, trimmed]);
    }
    setTagInput('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t !== tagToRemove));
  };

  const handleFileDrop = (e: React.DragEvent | React.ChangeEvent<HTMLInputElement>) => {
    setFileError(null);
    let file: File | null = null;
    if ('dataTransfer' in e && e.dataTransfer.files.length > 0) {
      file = e.dataTransfer.files[0];
    } else if ('target' in e) {
      const input = e.target as HTMLInputElement;
      if (input.files && input.files.length > 0) {
        file = input.files[0];
      }
    }

    if (!file) return;

    const lowerName = file.name.toLowerCase();
    const isCsv = lowerName.endsWith('.csv');
    const isXlsx = lowerName.endsWith('.xlsx');

    if (!isCsv && !isXlsx) {
      setFileError('Invalid file type. Drop zone accepts ONLY CSV and XLSX files.');
      return;
    }

    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > 50) {
      setFileError('File exceeds maximum size of 50 MB.');
      return;
    }

    setSelectedFile({
      name: file.name,
      sizeMb: +sizeMb.toFixed(2),
      type: isCsv ? 'csv' : 'xlsx',
    });

    // Simulate progress
    setFileProgress(0);
    const interval = setInterval(() => {
      setFileProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 25;
      });
    }, 150);
  };

  const startLiveEvaluation = () => {
    setCurrentStep(3);
    setIsEvaluating(true);
    setEvaluationComplete(false);
    setEvalProgress(0);
    setEvalStageIndex(0);

    const stagesCount = 5;
    let currentIdx = 0;

    const interval = setInterval(() => {
      currentIdx += 1;
      setEvalStageIndex(currentIdx);
      setEvalProgress(Math.min(100, Math.round((currentIdx / stagesCount) * 100)));

      if (currentIdx >= stagesCount) {
        clearInterval(interval);
        setIsEvaluating(false);
        setEvaluationComplete(true);
      }
    }, 500);
  };

  const handleFinalViewInMarketplace = () => {
    const newDs: AppDataset = {
      id: `ds-${Date.now()}`,
      name: selectedFile ? selectedFile.name : `${name.toLowerCase().replace(/\s+/g, '_')}.csv`,
      title: name,
      description,
      domain: category,
      format: selectedFile ? selectedFile.type : 'csv',
      authorId: currentUser.id,
      authorName: currentUser.name,
      cost: 20,
      qualityScore,
      relevanceScore,
      overallScore,
      status: 'APPROVED',
      tags: tags.length > 0 ? tags : ['telecom', 'churn'],
      license,
      usageCount: 0,
      qualityBreakdown: {
        completeness: 88,
        validity: 92,
        uniqueness: 84,
        consistency: 76,
      },
      rowCount: 14200,
      columnCount: 6,
      columns: [
        { name: 'customer_id', type: 'UUID', nullCount: 0, nullPct: 0, distinctCount: 14200, synonyms: ['id', 'user_id', 'subscriber_id'], description: 'Unique customer identifier' },
        { name: 'tenure_months', type: 'Int64', nullCount: 12, nullPct: 0.08, distinctCount: 72, synonyms: ['tenure', 'months_active'], description: 'Months of subscription' },
        { name: 'monthly_charges', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 1840, synonyms: ['monthly_spend', 'bill_amount'], description: 'Monthly fee' },
        { name: 'contract_type', type: 'Categorical', nullCount: 0, nullPct: 0, distinctCount: 3, synonyms: ['contract', 'plan_type'], description: 'Month-to-month, 1-yr, 2-yr' },
        { name: 'total_charges', type: 'Float64 ($)', nullCount: 15, nullPct: 0.1, distinctCount: 12400, synonyms: ['lifetime_value', 'total_spend'], description: 'Total charges billed' },
        { name: 'churn_status', type: 'Boolean', nullCount: 0, nullPct: 0, distinctCount: 2, synonyms: ['churn', 'cancelled', 'attrition'], description: 'Yes or No' },
      ],
      previewRows: [
        { customer_id: 'C-90412', tenure_months: 1, monthly_charges: 29.85, contract_type: 'Month-to-month', total_charges: 29.85, churn_status: 'No' },
        { customer_id: 'C-90413', tenure_months: 34, monthly_charges: 56.95, contract_type: 'One year', total_charges: 1889.50, churn_status: 'No' },
        { customer_id: 'C-90414', tenure_months: 2, monthly_charges: 53.85, contract_type: 'Month-to-month', total_charges: 108.15, churn_status: 'Yes' },
        { customer_id: 'C-90415', tenure_months: 45, monthly_charges: 42.30, contract_type: 'One year', total_charges: 1840.75, churn_status: 'No' },
        { customer_id: 'C-90416', tenure_months: 2, monthly_charges: 70.70, contract_type: 'Month-to-month', total_charges: 151.65, churn_status: 'Yes' },
      ],
      createdAt: new Date().toISOString().split('T')[0],
      currentVersion: 'v1.0',
      versionHistory: [
        {
          version: 'v1.0',
          date: new Date().toISOString().split('T')[0],
          author: currentUser.name,
          quality: qualityScore,
          relevance: relevanceScore,
          changesSummary: 'Initial dataset upload with automated schema clearance.',
        },
      ],
      unlockedBy: [currentUser.id],
      sampleQueries: [
        'Show high churn customers with monthly spend over 60',
        'Average tenure of churned customers vs retained',
        'Count of customers grouped by contract type'
      ],
    };

    onPublishDataset(newDs, earnedCredits);
    onNavigate('marketplace');
  };

  const evalStages = [
    'Preprocessing',
    'Relevance check',
    'Quality check',
    'Scoring',
    'Credit calculation',
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Stepper Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
              Dataset Contribution Pipeline
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              Upload Wizard
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Submit structured data and earn credits via automated schema evaluation.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {[1, 2, 3].map((step) => (
              <div key={step} className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                    currentStep === step
                      ? 'bg-indigo-600 text-white'
                      : currentStep > step
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {currentStep > step ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : step}
                </div>
                {step < 3 && <div className="w-6 h-0.5 bg-slate-200" />}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Step 1: Details */}
      {currentStep === 1 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-6">
          <div className="border-b border-slate-100 pb-3">
            <h2 className="text-base font-bold text-slate-900">
              Step 1: Dataset Details
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Specify dataset metadata, category, searchable tag chips, and open license.
            </p>
          </div>

          <div className="space-y-4">
            {/* Name (3-80 chars) */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <label className="font-semibold text-slate-700">Dataset Name</label>
                <span className={`font-mono ${isNameValid ? 'text-slate-400' : 'text-red-500'}`}>
                  {name.trim().length}/80 chars (min 3)
                </span>
              </div>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={`w-full bg-slate-50 border rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none ${
                  isNameValid ? 'border-slate-300 focus:border-indigo-500' : 'border-red-300 focus:border-red-500'
                }`}
                placeholder="e.g. Telecom Customer Churn Q4"
              />
              {!isNameValid && (
                <p className="text-[11px] text-red-500 mt-1">
                  Name must be between 3 and 80 characters.
                </p>
              )}
            </div>

            {/* Description (10-1000 chars) */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <label className="font-semibold text-slate-700">Description</label>
                <span className={`font-mono ${isDescValid ? 'text-slate-400' : 'text-red-500'}`}>
                  {description.trim().length}/1000 chars (min 10)
                </span>
              </div>
              <textarea
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className={`w-full bg-slate-50 border rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none ${
                  isDescValid ? 'border-slate-300 focus:border-indigo-500' : 'border-red-300 focus:border-red-500'
                }`}
                placeholder="Summarize the dataset content, schema attributes, and business usage context..."
              />
              {!isDescValid && (
                <p className="text-[11px] text-red-500 mt-1">
                  Description must be between 10 and 1000 characters.
                </p>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Category */}
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Category
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                >
                  <option value="Healthcare">Healthcare</option>
                  <option value="Telecom">Telecom</option>
                  <option value="Retail">Retail</option>
                  <option value="Finance">Finance</option>
                  <option value="Education">Education</option>
                  <option value="Technology">Technology</option>
                  <option value="General">General</option>
                </select>
              </div>

              {/* License */}
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  License
                </label>
                <select
                  value={license}
                  onChange={(e) => setLicense(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                >
                  <option value="MIT">MIT License</option>
                  <option value="Open Data Commons">Open Data Commons</option>
                  <option value="CC-BY-4.0">Creative Commons CC-BY-4.0</option>
                  <option value="Apache 2.0">Apache 2.0</option>
                </select>
              </div>
            </div>

            {/* Tags as Chips (Max 10) */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <label className="font-semibold text-slate-700">Tags (Max 10 chips)</label>
                <span className="text-slate-400 font-mono">{tags.length}/10</span>
              </div>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                  disabled={tags.length >= 10}
                  placeholder={tags.length >= 10 ? 'Tag limit reached' : 'Type a tag and press Enter...'}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
                <button
                  type="button"
                  onClick={handleAddTag}
                  disabled={tags.length >= 10 || !tagInput.trim()}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 disabled:opacity-40 text-slate-700 rounded-lg text-xs font-medium cursor-pointer transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 min-h-[32px] p-2 bg-slate-50 border border-slate-200 rounded-lg">
                {tags.length === 0 ? (
                  <span className="text-[11px] text-slate-400 italic">No tags added yet.</span>
                ) : (
                  tags.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700 border border-indigo-200"
                    >
                      <span>#{t}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveTag(t)}
                        className="hover:text-red-600 cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-slate-100">
            <button
              onClick={() => setCurrentStep(2)}
              disabled={!canProceedStep1}
              className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer flex items-center gap-2"
            >
              <span>Next: File Upload</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Step 2: File Drop Zone */}
      {currentStep === 2 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-6">
          <div className="border-b border-slate-100 pb-3">
            <h2 className="text-base font-bold text-slate-900">
              Step 2: File Upload
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload your structured data file. Accepting ONLY CSV and XLSX files up to 50 MB.
            </p>
          </div>

          {/* File Drop Zone (accepting ONLY CSV and XLSX up to 50 MB) */}
          <label
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              handleFileDrop(e);
            }}
            className="block border-2 border-dashed border-slate-300 hover:border-indigo-400 rounded-xl p-8 text-center transition-colors bg-slate-50/50 cursor-pointer"
          >
            <input
              type="file"
              accept=".csv,.xlsx"
              onChange={handleFileDrop}
              className="hidden"
            />
            <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mx-auto mb-3">
              <Upload className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-800">
              Drop file here or click to browse
            </h3>
            {/* Helper text required: CSV or XLSX, up to 50 MB */}
            <p className="text-xs text-slate-500 mt-1 font-medium">
              CSV or XLSX, up to 50 MB
            </p>
          </label>

          {fileError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{fileError}</span>
            </div>
          )}

          {/* Selected File Card with Progress Bar */}
          {selectedFile && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <FileCode className="w-4 h-4 text-indigo-600" />
                  <span className="font-semibold text-slate-800">{selectedFile.name}</span>
                  <span className="font-mono text-slate-400">({selectedFile.sizeMb} MB)</span>
                </div>
                <span className="font-mono font-bold text-emerald-600">{fileProgress}%</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${fileProgress}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <button
              onClick={() => setCurrentStep(1)}
              className="text-xs font-medium text-slate-500 hover:text-slate-700 cursor-pointer flex items-center gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Details</span>
            </button>

            <button
              onClick={startLiveEvaluation}
              disabled={!selectedFile || fileProgress < 100}
              className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer flex items-center gap-2"
            >
              <span>Continue to Live Evaluation</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Live Evaluation & Credit Breakdown */}
      {currentStep === 3 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-6">
          <div className="border-b border-slate-100 pb-3">
            <h2 className="text-base font-bold text-slate-900">
              Step 3: Live Evaluation & Rewards
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Automated evaluation pipeline verifies schema fidelity, completeness, and domain relevance.
            </p>
          </div>

          {/* Live Evaluation Stages: Preprocessing, Relevance check, Quality check, Scoring, Credit calculation */}
          <div className="space-y-4">
            <div className="flex justify-between text-xs font-semibold">
              <span className="text-slate-700">Evaluation Progress</span>
              <span className="font-mono text-indigo-600">{evalProgress}%</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${evalProgress}%` }}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 pt-2">
              {evalStages.map((stg, idx) => {
                const isPassed = evalStageIndex > idx || evaluationComplete;
                const isCurrent = evalStageIndex === idx && isEvaluating;

                return (
                  <div
                    key={stg}
                    className={`p-3 rounded-lg border text-center transition-colors text-xs ${
                      isPassed
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : isCurrent
                        ? 'bg-indigo-50 border-indigo-200 text-indigo-700 font-semibold'
                        : 'bg-slate-50 border-slate-200 text-slate-400'
                    }`}
                  >
                    <div className="text-[10px] uppercase font-bold tracking-wider mb-0.5">
                      Stage {idx + 1}
                    </div>
                    <div>{stg}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Results: Three Score Gauges and Credit Breakdown Card */}
          {evaluationComplete && (
            <div className="space-y-6 pt-4 border-t border-slate-100">
              {/* Three Score Gauges */}
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide block mb-1">
                    Quality
                  </span>
                  <span className="text-3xl font-black font-mono text-slate-900">{qualityScore}</span>
                  <span className="text-[10px] text-slate-400 block mt-1">out of 100</span>
                </div>

                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide block mb-1">
                    Relevance
                  </span>
                  <span className="text-3xl font-black font-mono text-slate-900">{relevanceScore}</span>
                  <span className="text-[10px] text-slate-400 block mt-1">out of 100</span>
                </div>

                <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200">
                  <span className="text-xs font-medium text-indigo-700 uppercase tracking-wide block mb-1">
                    Overall
                  </span>
                  <span className="text-3xl font-black font-mono text-indigo-700">{overallScore}</span>
                  <span className="text-[10px] text-indigo-500 block mt-1">(Qual + Rel) / 2</span>
                </div>
              </div>

              {/* Exact Credit Breakdown Card: "Basic +50, Quality bonus +25, Relevance bonus +15 = 90 credits" */}
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 space-y-2">
                <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider block">
                  Reward Breakdown
                </span>
                <div className="text-lg sm:text-xl font-bold font-mono text-emerald-700">
                  Basic +50, Quality bonus +25, Relevance bonus +15 = 90 credits
                </div>
                <p className="text-xs text-emerald-600">
                  Published datasets are indexed for instant plain English queries. You will also earn +20 credits each time another user unlocks this dataset.
                </p>
              </div>

              {/* Button: "View in marketplace" */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={handleFinalViewInMarketplace}
                  className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-sm cursor-pointer flex items-center gap-2 transition-colors"
                >
                  <Coins className="w-4 h-4" />
                  <span>View in marketplace</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
