import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Search,
  Lock,
  Unlock,
  AlertCircle,
  RefreshCw,
  Loader2,
  Library,
  Users,
  User,
  Sparkles,
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

type LibrarySourceTab = 'all' | 'mine' | 'community' | 'curated';

function buildPageWindow(current: number, total: number): (number | 'ellipsis')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages: (number | 'ellipsis')[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) pages.push('ellipsis');
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < total - 1) pages.push('ellipsis');
  pages.push(total);
  return pages;
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
  const [librarySource, setLibrarySource] = useState<LibrarySourceTab>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [minQuality, setMinQuality] = useState<number>(0);
  const [maxCost, setMaxCost] = useState<number | null>(null);
  const [selectedLicense, setSelectedLicense] = useState<string>('All');
  const [sortBy, setSortBy] = useState<'match' | 'quality' | 'newest' | 'usage'>('match');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 12;

  const [realDatasets, setRealDatasets] = useState<AppDataset[]>(propDatasets);
  const [knownCategories, setKnownCategories] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const catalogByIdRef = useRef<Map<string, AppDataset>>(
    new Map(propDatasets.map((d) => [d.id, d]))
  );

  useEffect(() => {
    if (propDatasets.length > 0) {
      for (const ds of propDatasets) {
        catalogByIdRef.current.set(ds.id, ds);
      }
    }
  }, [propDatasets]);

  const fetchDatasets = useCallback(
    async (queryText: string, category: string) => {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const domainParam = category !== 'All' ? category : undefined;

        if (queryText.trim().length > 0) {
          const searchRes = await api.datasets.search(queryText.trim(), domainParam, 100);
          const mapped = searchRes.results
            .map((item) =>
              searchItemToAppDataset(
                item,
                currentUser.id,
                catalogByIdRef.current.get(item.dataset_id)
              )
            )
            .filter((ds) => !(ds.isCurated && ds.storageAvailable === false));
          setRealDatasets(mapped);
          setActiveQuery(queryText.trim());
        } else {
          // Fetch full accessible catalog so Category dropdown and Library tab counts stay intact
          const listRes = await api.datasets.list();
          const mapped = listRes.datasets
            .map((item) => backendDatasetToAppDataset(item, currentUser.id))
            .filter((ds) => !(ds.isCurated && ds.storageAvailable === false));
          catalogByIdRef.current = new Map(mapped.map((d) => [d.id, d]));
          setRealDatasets(mapped);
          setActiveQuery('');
          const cats = Array.from(
            new Map(
              mapped
                .map((d) => (d.domain || 'General').trim())
                .filter(Boolean)
                .map((d) => [d.toLowerCase(), d] as [string, string])
            ).values()
          ).sort((a, b) => a.localeCompare(b));
          setKnownCategories(cats);
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

  useEffect(() => {
    // Only re-fetch from server on category change when an active search query is present;
    // full catalog loads once on mount and filters categories client-side without shrinking options.
    if (searchQuery.trim().length > 0 || realDatasets.length === 0) {
      fetchDatasets(searchQuery, selectedCategory);
    }
  }, [selectedCategory]);

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

  // Dynamic filter options derived from live catalog (never silently hides valid domains, licenses, or prices)
  const dynamicCategories = useMemo(() => {
    const map = new Map<string, string>();
    for (const cat of knownCategories) {
      map.set(cat.toLowerCase(), cat);
    }
    for (const ds of realDatasets) {
      const dom = (ds.domain || 'General').trim();
      if (dom) {
        map.set(dom.toLowerCase(), dom);
      }
    }
    if (selectedCategory !== 'All' && !map.has(selectedCategory.toLowerCase())) {
      map.set(selectedCategory.toLowerCase(), selectedCategory);
    }
    return Array.from(map.values()).sort((a, b) => a.localeCompare(b));
  }, [knownCategories, realDatasets, selectedCategory]);

  const dynamicLicenses = useMemo(() => {
    const set = new Set<string>();
    for (const ds of realDatasets) {
      const lic = (ds.license || '').trim();
      if (lic) set.add(lic);
    }
    if (selectedLicense !== 'All') set.add(selectedLicense);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [realDatasets, selectedLicense]);

  const catalogMaxCost = useMemo(() => {
    let highest = 50;
    for (const ds of realDatasets) {
      const c = Number(ds.cost ?? ds.unlockPrice ?? 0);
      if (Number.isFinite(c) && c > highest) highest = Math.ceil(c);
    }
    return highest;
  }, [realDatasets]);

  const effectiveMaxCost = maxCost === null ? catalogMaxCost : Math.min(maxCost, catalogMaxCost);

  const sourceCounts = useMemo(() => {
    const accessible = realDatasets.filter(
      (ds) => ds.status !== 'REJECTED' && !(ds.isCurated && ds.storageAvailable === false)
    );
    const mine = accessible.filter(
      (ds) => ds.authorId === currentUser.id && !ds.isCurated
    ).length;
    const curated = accessible.filter((ds) => Boolean(ds.isCurated)).length;
    const community = accessible.filter(
      (ds) => !ds.isCurated && ds.visibility !== 'private'
    ).length;
    return { all: accessible.length, mine, community, curated };
  }, [realDatasets, currentUser.id]);

  const filtered = useMemo(() => {
    return realDatasets
      .filter((ds) => ds.status !== 'REJECTED' && !(ds.isCurated && ds.storageAvailable === false))
      .filter((ds) => {
        if (librarySource === 'mine' && (ds.authorId !== currentUser.id || ds.isCurated)) {
          return false;
        }
        if (librarySource === 'curated' && !ds.isCurated) {
          return false;
        }
        if (librarySource === 'community' && (ds.isCurated || ds.visibility === 'private')) {
          return false;
        }
        if (
          selectedCategory !== 'All' &&
          ds.domain.toLowerCase() !== selectedCategory.toLowerCase()
        ) {
          return false;
        }
        if (ds.qualityScore < minQuality) {
          return false;
        }
        if (maxCost !== null && ds.cost > effectiveMaxCost) {
          return false;
        }
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
  }, [
    realDatasets,
    librarySource,
    selectedCategory,
    minQuality,
    maxCost,
    effectiveMaxCost,
    selectedLicense,
    sortBy,
    activeQuery,
  ]);

  const totalPages = Math.ceil(filtered.length / itemsPerPage) || 1;
  const safePage = Math.min(currentPage, totalPages);
  const paginated = filtered.slice(
    (safePage - 1) * itemsPerPage,
    safePage * itemsPerPage
  );
  const pageWindow = buildPageWindow(safePage, totalPages);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Marketplace
          </h1>
          <p className="text-sm text-slate-500">
            Explore verified Curated Public Library datasets and Community Marketplace listings.
          </p>
        </div>

        <button
          onClick={() => onNavigate('upload')}
          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium cursor-pointer shadow-sm transition-colors self-start sm:self-auto"
        >
          Contribute New Dataset
        </button>
      </div>

      {/* Library Source Tabs: All (default), My Datasets, Community Datasets, Curated Library */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap rounded-xl bg-slate-100 p-1 border border-slate-200 gap-0.5">
          <button
            type="button"
            onClick={() => {
              setLibrarySource('all');
              setCurrentPage(1);
            }}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              librarySource === 'all'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <span>All</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600">
              {sourceCounts.all}
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setLibrarySource('mine');
              setCurrentPage(1);
            }}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              librarySource === 'mine'
                ? 'bg-white text-amber-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <User className="w-3.5 h-3.5" />
            <span>My Datasets</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-amber-50 text-amber-700">
              {sourceCounts.mine}
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setLibrarySource('community');
              setCurrentPage(1);
            }}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              librarySource === 'community'
                ? 'bg-white text-emerald-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Community Datasets</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-50 text-emerald-700">
              {sourceCounts.community}
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setLibrarySource('curated');
              setCurrentPage(1);
            }}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              librarySource === 'curated'
                ? 'bg-white text-indigo-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Library className="w-3.5 h-3.5" />
            <span>Curated Library</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-indigo-50 text-indigo-700">
              {sourceCounts.curated}
            </span>
          </button>
        </div>

        <span className="text-xs text-slate-500">
          Showing <strong className="text-slate-800">{filtered.length}</strong> dataset{filtered.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
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

        {/* Dynamic Filters Row */}
        <div className="pt-3 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Dynamic Category Filter */}
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
              {dynamicCategories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
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

          {/* Dynamic Maximum Cost Slider (defaults to uncapped catalog max) */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="text-slate-500 font-medium">Max Cost</label>
              <span className="font-mono font-bold text-slate-700">
                {maxCost === null ? `Any (≤${catalogMaxCost} cr)` : `${effectiveMaxCost} credits`}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max={catalogMaxCost}
              value={effectiveMaxCost}
              onChange={(e) => {
                const v = Number(e.target.value);
                setMaxCost(v >= catalogMaxCost ? null : v);
                setCurrentPage(1);
              }}
              className="w-full accent-indigo-600 cursor-pointer"
            />
          </div>

          {/* Dynamic License Filter */}
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
              {dynamicLicenses.map((lic) => (
                <option key={lic} value={lic}>
                  {lic}
                </option>
              ))}
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

      {/* Network Error State */}
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

      {/* Loading Spinner */}
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
              : 'No datasets found. Adjust your filters or contribute a dataset to the marketplace.'}
          </div>
        ) : (
          paginated.map((ds) => {
            const isCurated = Boolean(ds.isCurated);
            const isOwner = ds.authorId === currentUser.id;
            const isUnlocked = isCurated || isOwner || ds.unlockedBy.includes(currentUser.id);
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
                      {isCurated ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1">
                          <Sparkles className="w-3 h-3" /> Curated Public
                        </span>
                      ) : ds.visibility === 'private' ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1">
                          <Lock className="w-3 h-3" /> Private
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Community
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {ds.domain}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-600 border border-slate-200">
                        {ds.format}
                      </span>
                      {matchScore !== null && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {matchScore}% match
                        </span>
                      )}
                    </div>

                    {/* Access / Cost Badge */}
                    {isCurated ? (
                      <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded shrink-0">
                        Free · 0 cr
                      </span>
                    ) : isOwner ? (
                      <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded shrink-0">
                        Author · {ds.unlockPrice ?? ds.cost ?? 10} cr
                      </span>
                    ) : isUnlocked ? (
                      <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded flex items-center gap-1 shrink-0">
                        <Unlock className="w-3 h-3" /> Unlocked · {ds.unlockPrice ?? ds.cost ?? 10} cr
                      </span>
                    ) : (
                      <span className="text-[11px] font-semibold text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded flex items-center gap-1 shrink-0">
                        <Lock className="w-3 h-3" /> {ds.unlockPrice ?? ds.cost ?? 10} cr unlock
                      </span>
                    )}
                  </div>

                  <div>
                    <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                      {ds.title}
                    </h3>
                    <span className="text-[11px] font-mono text-slate-400 block mb-1">
                      {isCurated && ds.sourceName ? `${ds.sourceName} · ${ds.name}` : ds.name}
                    </span>
                    <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                      {ds.description}
                    </p>
                  </div>

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
                <div className="pt-4 mt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-3 text-slate-500">
                    {ds.availability && (
                      <span
                        className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                          ds.storageAvailable
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border-amber-200'
                        }`}
                      >
                        {ds.availability}
                      </span>
                    )}
                    {ds.rowCount > 0 && (
                      <span className="font-mono text-slate-500">
                        {ds.rowCount.toLocaleString()} rows
                      </span>
                    )}
                    {ds.overallScore > 0 && (
                      <span>
                        Score: <strong className="font-mono text-indigo-700">{ds.overallScore}</strong>
                      </span>
                    )}
                    {ds.qualityScore > 0 && ds.qualityScore !== ds.overallScore && (
                      <span>
                        Quality: <strong className="font-mono text-slate-700">{ds.qualityScore}</strong>
                      </span>
                    )}
                  </div>

                  <span className="text-slate-400 text-[11px] truncate max-w-[200px]" title={ds.license}>
                    {ds.license}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Scalable Windowed Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1.5 pt-4 flex-wrap">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={safePage === 1}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Previous
          </button>

          {pageWindow.map((entry, idx) =>
            entry === 'ellipsis' ? (
              <span key={`ell_${idx}`} className="px-2 text-xs text-slate-400">
                …
              </span>
            ) : (
              <button
                key={entry}
                onClick={() => setCurrentPage(entry)}
                className={`min-w-8 h-8 px-2 rounded-lg text-xs font-semibold cursor-pointer transition-colors ${
                  safePage === entry
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {entry}
              </button>
            )
          )}

          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={safePage === totalPages}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
