'use client';

import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Check, Search, X } from 'lucide-react';
import './workspace-select.css';
import './hospital-search.css';

import { matchHospitals, type HospitalOption } from '@/lib/hospital-search';

/** Search box that suggests hospitals as you type (ARIA combobox with a listbox popup). */
export default function HospitalSearch({ label, value, options, onChange, disabled = false, placeholder = 'Search for a hospital' }: {
  label: string; value: string; options: HospitalOption[]; onChange: (id: string) => void;
  disabled?: boolean; placeholder?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const selected = options.find(option => option.id === value);
  const [query, setQuery] = useState(selected?.name ?? '');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [editing, setEditing] = useState(false);
  // Show the chosen hospital's name whenever the choice changes from outside.
  useEffect(() => { if (!editing) setQuery(selected?.name ?? ''); }, [selected?.name, editing]);
  const suggestions = matchHospitals(options, editing ? query : '');
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);

  function choose(option: HospitalOption | undefined) {
    if (!option) return;
    onChange(option.id);
    setQuery(option.name);
    setEditing(false);
    setOpen(false);
  }
  function clear() {
    onChange('');
    setQuery('');
    setEditing(true);
    setOpen(true);
    setActive(0);
    input.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) { setOpen(true); return; }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive(index => Math.max(0, Math.min(suggestions.length - 1, index + step)));
    } else if (event.key === 'Enter' && open) {
      event.preventDefault();
      choose(suggestions[active]);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      setEditing(false);
      setQuery(selected?.name ?? '');
    }
  }

  const listId = `${id}-suggestions`;
  return (
    <div className="ws-select hs-search">
      <div className="hs-field" data-disabled={disabled || undefined}>
        <Search size={15} aria-hidden="true" />
        <input ref={input} type="text" role="combobox" aria-label={label} aria-autocomplete="list"
          aria-expanded={open} aria-controls={listId} disabled={disabled} placeholder={placeholder}
          aria-activedescendant={open && suggestions[active] ? `${id}-option-${active}` : undefined}
          value={query} autoComplete="off" spellCheck={false}
          onFocus={event => { event.currentTarget.select(); setOpen(true); setActive(0); }}
          onChange={event => { setQuery(event.target.value); setEditing(true); setOpen(true); setActive(0); }}
          onBlur={() => { setOpen(false); setEditing(false); setQuery(selected?.name ?? ''); }}
          onKeyDown={keyDown} />
        {(query || value) && !disabled && (
          <button type="button" className="text-button hs-clear" aria-label="Clear hospital search"
            onPointerDown={event => event.preventDefault()} onClick={clear}><X size={14} aria-hidden="true" /></button>
        )}
      </div>
      {open && (
        <ul ref={list} id={listId} className="ws-select-options hs-options" role="listbox" aria-label={label}>
          {suggestions.length ? suggestions.map((option, index) => (
            <li key={option.id} id={`${id}-option-${index}`} data-index={index} role="option"
              aria-selected={option.id === value} data-active={index === active}
              onPointerMove={() => setActive(index)} onPointerDown={event => event.preventDefault()}
              onClick={() => choose(option)}>
              <span>{option.name}{option.note && <small>{option.note}</small>}</span>
              {option.id === value && <Check size={14} aria-hidden="true" />}
            </li>
          )) : <li className="hs-empty" role="presentation">No hospital matches “{query}”.</li>}
        </ul>
      )}
    </div>
  );
}
