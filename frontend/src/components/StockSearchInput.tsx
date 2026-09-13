"use client";

import React, { useState, useEffect, useRef } from "react";
import { Search, X, Check } from "lucide-react";
import { getStocks } from "@/lib/api";
import { Stock } from "@/lib/types";

interface StockSearchInputProps {
  selectedTicker?: string;
  selectedStock?: Stock | null;
  onSelect: (stock: Stock) => void;
  placeholder?: string;
}

export default function StockSearchInput({
  selectedTicker,
  selectedStock: selectedStockProp,
  onSelect,
  placeholder = "ابحث بالرمز، أو اسم الشركة بالعربي أو الإنجليزي...",
}: StockSearchInputProps) {
  const [query, setQuery] = useState("");
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(selectedStockProp || null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedStockProp) {
      setSelectedStock(selectedStockProp);
      setQuery(`${selectedStockProp.ticker} - ${selectedStockProp.arabic_name}`);
    } else if (!selectedTicker) {
      setSelectedStock(null);
      setQuery("");
    }
  }, [selectedStockProp, selectedTicker]);

  useEffect(() => {
    if (!selectedTicker || selectedStockProp) return;

    getStocks({ q: selectedTicker })
      .then((res) => {
        const normalizedTicker = selectedTicker.trim().toUpperCase();

        const match = res.items.find(
          (s) => s.ticker.toUpperCase() === normalizedTicker
        );

        if (match) {
          setSelectedStock(match);
          setQuery(`${match.ticker} - ${match.arabic_name}`);
          onSelect(match);
        }
      })
      .catch(() => null);
  }, [selectedTicker, selectedStockProp, onSelect]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen && query.length === 0) return;

    const timer = setTimeout(() => {
      setLoading(true);
      getStocks({ q: query })
        .then((res) => {
          setStocks(res.items);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    }, 200);

    return () => clearTimeout(timer);
  }, [query, isOpen]);

  const handleSelect = (stock: Stock) => {
    setSelectedStock(stock);
    setQuery(`${stock.ticker} - ${stock.arabic_name}`);
    setIsOpen(false);
    onSelect(stock);
  };

  const handleClear = () => {
    setQuery("");
    setSelectedStock(null);
    setIsOpen(true);
  };

  return (
    <div className="relative w-full" ref={containerRef}>
      <div className="relative flex items-center">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder={placeholder}
          className="w-full bg-surface border border-surfaceBorder rounded-lg px-4 py-3 pl-10 pr-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
        />
        <Search className="w-5 h-5 text-gray-400 absolute right-3 pointer-events-none" />
        {query && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute left-3 text-gray-400 hover:text-white p-1"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Autocomplete Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-surface border border-surfaceBorder rounded-lg shadow-2xl max-h-72 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-xs text-gray-400">جاري البحث في أسهم EGX...</div>
          ) : stocks.length === 0 ? (
            <div className="p-4 text-center text-xs text-gray-400">لا توجد أسهم مطابقة في البورصة المصرية</div>
          ) : (
            <ul className="divide-y divide-surfaceBorder">
              {stocks.map((stock) => {
                const isSelected = selectedStock?.ticker === stock.ticker;
                return (
                  <li
                    key={stock.ticker}
                    onClick={() => handleSelect(stock)}
                    className="p-3 hover:bg-surfaceHover cursor-pointer flex items-center justify-between transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-primary font-mono text-sm bg-primary/10 px-2 py-0.5 rounded">
                        {stock.ticker}
                      </span>
                      <div>
                        <div className="text-sm font-medium text-white">{stock.arabic_name}</div>
                        <div className="text-xs text-gray-400">{stock.english_name}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] px-2 py-0.5 rounded bg-surfaceHover text-gray-300 border border-surfaceBorder">
                        {stock.sector}
                      </span>
                      {isSelected && <Check className="w-4 h-4 text-primary" />}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}