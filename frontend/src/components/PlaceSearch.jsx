import React, { useEffect, useRef, useState } from 'react';
import { MapPin, Search, X } from 'lucide-react';
import { api } from '../api';

export default function PlaceSearch({ label, value, onChange, placeholder = 'Search area, landmark or address' }) {
  const [query, setQuery] = useState(value?.name || '');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [highlight, setHighlight] = useState(-1);
  const box = useRef(null);
  useEffect(() => { setQuery(value?.name || ''); }, [value?.name]);
  useEffect(() => {
    const close = e => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close); return () => document.removeEventListener('mousedown', close);
  }, []);
  useEffect(() => {
    if (query.trim().length < 2 || (value && query === value.name)) { setResults([]); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true); setError('');
      try {
        const data = await api(`/places/search?q=${encodeURIComponent(query)}`);
        setResults(data.results || []); setOpen(true); setHighlight(-1);
        if (!data.results?.length) setError('No matching places. Try a nearby landmark or a different spelling.');
      } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
      finally { setBusy(false); }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, value?.name]);
  const choose = place => { onChange(place); setQuery(place.name); setOpen(false); setError(''); };
  const key = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight(h => Math.min(h + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight(h => Math.max(h - 1, 0)); }
    else if (e.key === 'Enter' && open && highlight >= 0) { e.preventDefault(); choose(results[highlight]); }
    else if (e.key === 'Escape') setOpen(false);
  };
  return <div className="place-search" ref={box}>
    <label>{label}</label>
    <div className={`place-input ${value ? 'selected' : ''}`}>
      {value ? <MapPin size={17} /> : <Search size={17} />}
      <input role="combobox" aria-expanded={open} aria-autocomplete="list" aria-label={label} value={query} placeholder={placeholder}
        onChange={e => { setQuery(e.target.value); if (value) onChange(null); }} onFocus={() => results.length && setOpen(true)} onKeyDown={key} />
      {busy && <span className="mini-spin" />}
      {value && <button type="button" className="icon-btn" aria-label="Clear location" onClick={() => { onChange(null); setQuery(''); setResults([]); }}><X size={15} /></button>}
    </div>
    {open && results.length > 0 && <ul className="place-results" role="listbox">
      {results.map((p, i) => <li key={`${p.id}-${i}`} role="option" aria-selected={i === highlight} className={i === highlight ? 'highlight' : ''} onMouseDown={e => { e.preventDefault(); choose(p); }} onMouseEnter={() => setHighlight(i)}>
        <MapPin size={16} /><div><strong>{p.name}</strong><small>{p.subtitle}</small></div>
      </li>)}
    </ul>}
    {error && <small className="field-error">{error}</small>}
    {value && <small className="field-hint">Selected: {value.lat.toFixed(4)}, {value.lng.toFixed(4)}</small>}
  </div>;
}
