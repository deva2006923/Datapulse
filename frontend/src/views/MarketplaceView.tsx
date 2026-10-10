import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search,
  Lock,
  Unlock,
  Coins,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { AppDataset, UserAccount, PageRoute } from '../types';
import { api, ApiError } from '../services/api';
import {
  backendDatasetToAppDataset,
  searchItemToAppDataset,
} from '../services/datasetAdapter';

interface MarketplaceViewProps {
  datasets?: AppDataset[];
  currentUser: UserAccount;
  onSelectDatasetForDetail: (datasetId: string) => void;
  onNavigate: (route: PageRoute) => void;
  onDatasetsLoaded?: (datasets: AppDataset[]) => void;
}

export const MarketplaceView: React.FC<MarketplaceViewProps> = ({
  datasets: propDatasets = [],
  currentUser,
  onSelectDatasetForDetail,
  onNavigate,
  onDatasetsLoaded,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [minQuality, setMinQuality] = useState<number>(0);
  const [maxCost, setMaxCost] = useState<number>(50);
  const [selectedLicense, setSelectedLicense] = useState<string>('All');
  const [sortBy, setSortBy] = useState<'match' | 'quality' | 'newest' | 'usage'>('match');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 4;

  const [realDatasets, setRealDatasets] = useState<AppDataset[]>(propDatasets);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchDatasets = useCallback(
    async (queryText: string, category: string) => {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const domainParam = category !== 'All' ? category.toLowerCase() : undefined;

        if (queryText.trim().length > 0) {
          // POST /datasets/search
          const searchRes = await api.datasets.search(queryText.trim(), domainParam);
          const mapped = searchRes.results.map((item) =>
            searchItemToAppDataset(item, currentUser.id)
          );
          setRealDatasets(mapped);
          setActiveQuery(queryText.trim());
          if (onDatasetsLoaded) {
            onDatasetsLoaded(mapped);
          }
        } else {
          // GET /datasets?domain=...
          const listRes = await api.datasets.list(domainParam);
          const mapped = listRes.datasets.map((item) =>
            backendDatasetToAppDataset(item, currentUser.id)
          );
          setRealDatasets(mapped);
          setActiveQuery('');
          if (onDatasetsLoaded) {
            onDatasetsLoaded(mapped);
          }
        }
      } catch (err: any) {
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unable to retrieve datasets from backend server. Please check your network connection.';
        setErrorMessage(message);
      } finally {
        setIsLoading(false);
      }
    },
    [currentUser.id, onDatasetsLoaded]
  );

  // Initial fetch and on category filter change
  useEffect(() => {
    fetchDatasets(searchQuery, selectedCategory);
  }, [selectedCategory]);

  // Handle Search Input Change with Debounce (400ms)
  const handleSearchInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearchQuery(val);
    setCurrentPage(1);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      fetchDatasets(val, selectedCategory);
    }, 350);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    fetchDatasets(searchQuery, selectedCategory);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setActiveQuery('');
    setCurrentPage(1);
    fetchDatasets('', selectedCategory);
  };

  // Filter datasets (approved catalog, min quality slider, max cost slider, license)
  const filtered = realDatasets
    .filter((ds) => ds.status !== 'REJECTED')
    .filter((ds) => {
      // Category filter (if backend didn't already filter or for hybrid verification)
      if (
        selectedCategory !== 'All' &&
        ds.domain.toLowerCase() !== selectedCategory.toLowerCase()
      ) {
        return false;
      }

      // Minimum quality slider
      if (ds.qualityScore < minQuality) {
        return false;
      }

      // Maximum cost slider
      if (ds.cost > maxCost) {
        return false;
      }

      // License filter
      if (selectedLicense !== 'All' && ds.license !== selectedLicense) {
        return false;
      }

      return true;
    })
    .sort((a, b) => {
      if (sortBy === 'match') {
        if (activeQuery) {
          return (b.matchScore ?? 0) - (a.matchScore ?? 0);
        }
        return b.overallScore - a.overallScore;
      }
      if (sortBy === 'quality') return b.qualityScore - a.qualityScore;
      if (sortBy === 'newest')
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      if (sortBy === 'usage') return (b.usageCount || 0) - (a.usageCount || 0);
      return 0;
    });

  const totalPages = Math.ceil(filtered.length / itemsPerPage) || 1;
  const paginated = filtered.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Marketplace
          </h1>
          <p className="text-sm text-slate-500">
            Explore verified datasets evaluated for quality and domain relevance.
          </p>
        </div>

        <button
          onClick={() => onNavigate('upload')}
          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium cursor-pointer shadow-sm transition-colors self-start sm:self-auto"
        >
          Contribute New Dataset
        </button>
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
        {/* Top Search Input & Sort */}
        <form
          onSubmit={handleSearchSubmit}
          className="flex flex-col md:flex-row items-center justify-between gap-3"
        >
          <div className="relative w-full md:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearchInputChange}
              placeholder='Search (e.g. "I need a dataset for predicting customer churn")...'
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-4 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
            />
            {isLoading && (
              <Loader2 className="w-3.5 h-3.5 text-indigo-500 absolute right-3 top-2.5 animate-spin" />
            )}
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto">
            <span className="text-xs text-slate-500 font-medium">Sort by:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5 text-xs text-slate-700 outline-none"
            >
              <option value="match">Best match</option>
              <option value="quality">Quality</option>
              <option value="newest">Newest</option>
              <option value="usage">Most used</option>
            </select>
          </div>
        </form>

        {/* Filters Controls Row (Category, Min Quality Slider, Max Cost Slider, License) */}
        <div className="pt-3 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Category Filter */}
          <div>
            <label className="text-slate-500 block mb-1 font-medium">Category</label>
            <select
              value={selectedCategory}
              onChange={(e) => {
                setSelectedCategory(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 outline-none"
            >
              <option value="All">All Categories</option>
              <option value="Healthcare">Healthcare</option>
              <option value="Telecom">Telecom</option>
              <option value="Retail">Retail</option>
              <option value="Finance">Finance</option>
              <option value="Education">Education</option>
              <option value="Technology">Technology</option>
            </select>
          </div>

          {/* Minimum Quality Slider */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="text-slate-500 font-medium">Min Quality</label>
              <span className="font-mono font-bold text-slate-700">{minQuality}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={minQuality}
              onChange={(e) => {
                setMinQuality(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="w-full accent-indigo-600 cursor-pointer"
            />
          </div>

          {/* Maximum Cost Slider */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="text-slate-500 font-medium">Max Cost</label>
              <span className="font-mono font-bold text-slate-700">{maxCost} credits</span>
            </div>
            <input
              type="range"
              min="0"
              max="50"
              value={maxCost}
              onChange={(e) => {
                setMaxCost(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="w-full accent-indigo-600 cursor-pointer"
            />
          </div>

          {/* License Filter */}
          <div>
            <label className="text-slate-500 block mb-1 font-medium">License</label>
            <select
              value={selectedLicense}
              onChange={(e) => {
                setSelectedLicense(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 outline-none"
            >
              <option value="All">All Licenses</option>
              <option value="MIT">MIT</option>
              <option value="Open Data Commons">Open Data Commons</option>
              <option value="CC-BY-4.0">CC-BY-4.0</option>
              <option value="Apache 2.0">Apache 2.0</option>
            </select>
          </div>
        </div>

        {activeQuery && (
          <div className="text-xs text-slate-500 pt-2 border-t border-slate-100 flex items-center justify-between">
            <span>
              Showing search results for <strong className="text-slate-800">"{activeQuery}"</strong> ({filtered.length} datasets found)
            </span>
            <button
              onClick={handleClearSearch}
              className="text-indigo-600 hover:underline cursor-pointer font-medium"
            >
              Clear Search
            </button>
          </div>
        )}
      </div>

      {/* Network Error State with Retry Button */}
      {errorMessage && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-3 text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => fetchDatasets(searchQuery, selectedCategory)}
            className="px-3 py-1 bg-white border border-red-300 rounded-lg text-red-700 font-semibold hover:bg-red-50 cursor-pointer flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Loading State Spinner */}
      {isLoading && realDatasets.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 space-y-3">
          <Loader2 className="w-6 h-6 text-indigo-600 animate-spin mx-auto" />
          <p className="text-xs font-semibold">Loading datasets from backend catalog...</p>
        </div>
      )}

      {/* Dataset Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {!isLoading && paginated.length === 0 ? (
          <div className="col-span-2 p-12 text-center text-slate-500 bg-white border border-slate-200 rounded-xl">
            {activeQuery
              ? `No datasets matched "${activeQuery}". Try adjusting your search term or category.`
              : 'No datasets found. Be the first to contribute a dataset to the marketplace!'}
          </div>
        ) : (
          paginated.map((ds) => {
            const isOwner = ds.authorId === currentUser.id;
            const isUnlocked = isOwner || ds.unlockedBy.includes(currentUser.id);
            const matchScore = ds.matchScore ?? null;

            return (
              <div
                key={ds.id}
                onClick={() => onSelectDatasetForDetail(ds.id)}
                className="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-5 shadow-sm transition-all cursor-pointer flex flex-col justify-between group"
              >
                <div className="space-y-3">
                  {/* Top Bar with Badges */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {ds.domain}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-600 border border-slate-200">
                        {ds.format}
                      </span>
                      {/* Real Match Score Badge from backend vector search */}
                      {matchScore !== null && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {matchScore}% match
                        </span>
                      )}
                    </div>

                    {/* Unlocked / Owner badge */}
                    {isOwner ? (
                      <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                        Author
                      </span>
                    ) : isUnlocked ? (
                      <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded flex items-center gap-1">
                        <Unlock className="w-3 h-3" /> Unlocked
                      </span>
                    ) : (
                      <span className="text-[11px] font-semibold text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded flex items-center gap-1">
                        <Lock className="w-3 h-3" /> {ds.cost} cr unlock
                      </span>
                    )}
                  </div>

                  <div>
                    <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                      {ds.title}
                    </h3>
                    <span className="text-[11px] font-mono text-slate-400 block mb-1">
                      {ds.name}
                    </span>
                    <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                      {ds.description}
                    </p>
                  </div>

                  {/* Tag Chips on Cards */}
                  {ds.tags && ds.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {ds.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-50 text-slate-500 border border-slate-200"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Card Bottom Ribbon */}
                <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3 text-slate-500">
                    <span>
                      Score: <strong className="font-mono text-indigo-700">{ds.overallScore}</strong>
                    </span>
                    <span>
                      Quality: <strong className="font-mono text-slate-700">{ds.qualityScore}</strong>
                    </span>
                    <span className="font-mono text-slate-400">
                      {ds.rowCount.toLocaleString()} rows
                    </span>
                  </div>

                  <span className="text-slate-400 text-[11px]">
                    License: {ds.license}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Previous
          </button>

          {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
            <button
              key={page}
              onClick={() => setCurrentPage(page)}
              className={`w-8 h-8 rounded-lg text-xs font-semibold cursor-pointer transition-colors ${
                currentPage === page
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {page}
            </button>
          ))}

          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
