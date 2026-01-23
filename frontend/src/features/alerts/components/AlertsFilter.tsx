import { Filter, X } from 'lucide-react';

interface AlertsFilterProps {
  selectedSymbol: string;
  onSymbolChange: (symbol: string) => void;
  limit: number;
  onLimitChange: (limit: number) => void;
  symbols: string[];
  hasFilters: boolean;
  onClear: () => void;
}

export function AlertsFilter({
  selectedSymbol,
  onSymbolChange,
  limit,
  onLimitChange,
  symbols,
  hasFilters,
  onClear,
}: AlertsFilterProps) {

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-gray-700 bg-gray-800/50 p-4">
      <div className="flex items-center gap-2 text-gray-400">
        <Filter className="h-4 w-4" />
        <span className="text-sm font-medium">Filters</span>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="symbol" className="text-sm text-gray-400">
          Symbol:
        </label>
        <select
          id="symbol"
          value={selectedSymbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="rounded-lg border border-gray-600 bg-gray-700 px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All Symbols</option>
          {symbols.map((symbol) => (
            <option key={symbol} value={symbol}>
              {symbol}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="limit" className="text-sm text-gray-400">
          Show:
        </label>
        <select
          id="limit"
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          className="rounded-lg border border-gray-600 bg-gray-700 px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value={25}>25</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
          <option value={200}>200</option>
        </select>
      </div>

      {hasFilters && (
        <button
          onClick={onClear}
          className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-gray-400 transition-colors hover:bg-gray-700 hover:text-gray-200"
        >
          <X className="h-4 w-4" />
          Clear
        </button>
      )}
    </div>
  );
}
