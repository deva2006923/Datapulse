import React, { useState } from 'react';
import {
  Upload,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  FileCode,
  Coins,
  X,
  Plus,
  AlertCircle,
} from 'lucide-react';
import { UserAccount, AppDataset, PageRoute, BackendDatasetDetail, ColumnDefinition } from '../types';
import { api } from '../services/api';

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
  const [selectedFile, setSelectedFile] = useState<{
    name: string;
    sizeMb: number;
    type: 'csv' | 'xlsx';
    rawFile?: File;
  } | null>(null);
  const [fileProgress, setFileProgress] = useState<number>(0);
  const [fileError, setFileError] = useState<string | null>(null);

  // Step 3: Live Evaluation & Backend Upload State
  const [evalProgress, setEvalProgress] = useState<number>(0);
  const [evalStageIndex, setEvalStageIndex] = useState<number>(0);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [evaluationComplete, setEvaluationComplete] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedDataset, setUploadedDataset] = useState<BackendDatasetDetail | null>(null);

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
      rawFile: file,
    });

    // Simulate upload selection progress
    setFileProgress(0);
    const interval = setInterval(() => {
      setFileProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 25;
      });
    }, 80);
  };

  const startLiveEvaluation = async () => {
    // Prevent duplicate submissions while upload or evaluation is running
    if (isUploading || isEvaluating) return;

    if (!selectedFile?.rawFile) {
      setFileError('Please select a valid CSV file before continuing.');
      return;
    }

    setCurrentStep(3);
    setIsUploading(true);
    setIsEvaluating(true);
    setEvaluationComplete(false);
    setUploadError(null);
    setUploadedDataset(null);
    setEvalProgress(10);
    setEvalStageIndex(0);

    const stagesCount = 5;
    let currentIdx = 0;
    const progressTimer = setInterval(() => {
      currentIdx = Math.min(currentIdx + 1, stagesCount - 1);
      setEvalStageIndex(currentIdx);
      setEvalProgress((prev) => Math.min(85, prev + 15));
    }, 600);

    try {
      const res = await api.datasets.upload(
        selectedFile.rawFile,
        category.toLowerCase(),
        name.trim()
      );

      clearInterval(progressTimer);
      setEvalStageIndex(5);
      setEvalProgress(100);
      setIsUploading(false);
      setIsEvaluating(false);
      setEvaluationComplete(true);
      setUploadedDataset(res);
    } catch (err: any) {
      clearInterval(progressTimer);
      setIsUploading(false);
      setIsEvaluating(false);
      setEvaluationComplete(false);
      setUploadError(err?.message || 'Failed to upload dataset to the backend server.');
    }
  };

  const handleFinalViewInMarketplace = () => {
    if (!uploadedDataset) return;

    const schemaEntries = Object.entries(uploadedDataset.schema_metadata || {});
    const columns: ColumnDefinition[] = schemaEntries.map(([colName, colType]) => ({
      name: colName,
      type: String(colType),
      nullCount: 0,
      nullPct: 0,
      distinctCount: 0,
      synonyms: [colName],
      description: `Column ${colName}`,
    }));

    const finalQuality = uploadedDataset.quality_score ?? 0;
    const finalRelevance = uploadedDataset.domain_relevance_score ?? 0;
    const finalOverall =
      uploadedDataset.overall_score ?? (finalQuality + finalRelevance) / 2;
    const finalCredits = uploadedDataset.credits_awarded ?? 0;

    const newDs: AppDataset = {
      id: uploadedDataset.id,
      name: uploadedDataset.filename,
      title: uploadedDataset.name || name,
      description: description || uploadedDataset.content_summary,
      domain:
        uploadedDataset.domain.charAt(0).toUpperCase() +
        uploadedDataset.domain.slice(1),
      format: 'csv',
      authorId: currentUser.id,
      authorName: currentUser.name,
      cost: 20,
      qualityScore: finalQuality,
      relevanceScore: finalRelevance,
      overallScore: finalOverall,
      status: 'APPROVED',
      tags: tags.length > 0 ? tags : [uploadedDataset.domain.toLowerCase()],
      license,
      usageCount: 0,
      qualityBreakdown: {
        completeness: finalQuality,
        validity: finalQuality,
        uniqueness: finalQuality,
        consistency: finalQuality,
      },
      rowCount: uploadedDataset.rows_count,
      columnCount: uploadedDataset.columns_count,
      columns,
      previewRows: [],
      createdAt: uploadedDataset.created_at
        ? uploadedDataset.created_at.split('T')[0]
        : new Date().toISOString().split('T')[0],
      currentVersion: 'v1.0',
      versionHistory: [
        {
          version: 'v1.0',
          date: new Date().toISOString().split('T')[0],
          author: currentUser.name,
          quality: finalQuality,
          relevance: finalRelevance,
          changesSummary:
            uploadedDataset.content_summary ||
            'Initial dataset upload with automated schema evaluation.',
        },
      ],
      unlockedBy: [currentUser.id],
      sampleQueries: [],
    };

    onPublishDataset(newDs, finalCredits);
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

          {/* File Drop Zone */}
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
              disabled={!selectedFile || !selectedFile.rawFile || fileProgress < 100 || isUploading}
              className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer flex items-center gap-2"
            >
              {isUploading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Uploading & Evaluating...</span>
                </>
              ) : (
                <>
                  <span>Continue to Live Evaluation</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
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

          {/* Live Evaluation Stages */}
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
                const isCurrent = evalStageIndex === idx && (isEvaluating || isUploading);

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

          {/* Backend Error State */}
          {uploadError && (
            <div className="space-y-4 pt-4 border-t border-slate-100">
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl space-y-2">
                <div className="flex items-center gap-2 text-red-700 font-bold text-sm">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <span>Upload & Evaluation Failed</span>
                </div>
                <p className="text-xs text-red-600 font-medium">
                  {uploadError}
                </p>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setUploadError(null);
                    setCurrentStep(2);
                  }}
                  className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs cursor-pointer flex items-center gap-1.5 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Back to File Upload</span>
                </button>

                <button
                  type="button"
                  onClick={startLiveEvaluation}
                  disabled={isUploading}
                  className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs cursor-pointer flex items-center gap-1.5 transition-colors"
                >
                  <span>Try Again</span>
                </button>
              </div>
            </div>
          )}

          {/* Results: Scores, Credit Breakdown, and Real Persisted Metadata */}
          {evaluationComplete && uploadedDataset && (
            <div className="space-y-6 pt-4 border-t border-slate-100">
              {/* Three Score Gauges */}
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide block mb-1">
                    Quality
                  </span>
                  <span className="text-3xl font-black font-mono text-slate-900">
                    {uploadedDataset.quality_score !== undefined
                      ? uploadedDataset.quality_score
                      : '—'}
                  </span>
                  <span className="text-[10px] text-slate-400 block mt-1">
                    {uploadedDataset.quality_score !== undefined
                      ? 'out of 100'
                      : 'Evaluation pending'}
                  </span>
                </div>

                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide block mb-1">
                    Relevance
                  </span>
                  <span className="text-3xl font-black font-mono text-slate-900">
                    {uploadedDataset.domain_relevance_score !== undefined
                      ? uploadedDataset.domain_relevance_score
                      : '—'}
                  </span>
                  <span className="text-[10px] text-slate-400 block mt-1">
                    {uploadedDataset.domain_relevance_score !== undefined
                      ? 'out of 100'
                      : 'Evaluation pending'}
                  </span>
                </div>

                <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200">
                  <span className="text-xs font-medium text-indigo-700 uppercase tracking-wide block mb-1">
                    Overall
                  </span>
                  <span className="text-3xl font-black font-mono text-indigo-700">
                    {uploadedDataset.overall_score !== undefined
                      ? uploadedDataset.overall_score
                      : '—'}
                  </span>
                  <span className="text-[10px] text-indigo-500 block mt-1">
                    {uploadedDataset.overall_score !== undefined
                      ? 'Composite Score'
                      : 'Evaluation pending'}
                  </span>
                </div>
              </div>

              {/* Reward Breakdown Card */}
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 space-y-2">
                <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider block">
                  Reward Breakdown
                </span>
                <div className="text-lg sm:text-xl font-bold font-mono text-emerald-700">
                  {uploadedDataset.credits_awarded !== undefined
                    ? `+${uploadedDataset.credits_awarded} credits awarded`
                    : 'Dataset verified and registered successfully'}
                </div>
                <p className="text-xs text-emerald-600">
                  Published datasets are indexed for instant plain English queries. You will also earn +20 credits each time another user unlocks this dataset.
                </p>
              </div>

              {/* Actual Backend Dataset Information */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b border-slate-200 pb-2.5">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <span className="text-xs font-bold text-slate-900 uppercase tracking-wide">
                      Persisted Dataset Details
                    </span>
                  </div>
                  <span className="font-mono text-xs px-2.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold self-start sm:self-auto">
                    ID: {uploadedDataset.id}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Filename</span>
                    <span className="font-semibold text-slate-800 break-all">{uploadedDataset.filename}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Domain</span>
                    <span className="font-semibold text-slate-800 capitalize">{uploadedDataset.domain}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Rows Count</span>
                    <span className="font-mono font-bold text-slate-800">{uploadedDataset.rows_count.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Columns Count</span>
                    <span className="font-mono font-bold text-slate-800">{uploadedDataset.columns_count}</span>
                  </div>
                </div>

                {uploadedDataset.content_summary && (
                  <p className="text-xs text-slate-600 pt-1 border-t border-slate-100">
                    {uploadedDataset.content_summary}
                  </p>
                )}

                {uploadedDataset.schema_metadata && Object.keys(uploadedDataset.schema_metadata).length > 0 && (
                  <div className="pt-2 border-t border-slate-100">
                    <span className="text-[11px] font-semibold text-slate-500 block mb-1.5">
                      Detected Schema Columns ({uploadedDataset.columns_count}):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(uploadedDataset.schema_metadata).map(([col, typ]) => (
                        <span
                          key={col}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-white border border-slate-200 text-slate-700"
                        >
                          <span className="font-semibold">{col}</span>
                          <span className="text-slate-400 text-[10px]">({String(typ)})</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Button: "View in marketplace" */}
              <div className="flex justify-end pt-2">
                <button
                  type="button"
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
