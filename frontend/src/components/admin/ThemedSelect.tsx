import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export interface ThemedSelectOption {
  value: string;
  label: string;
}

interface ThemedSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: ThemedSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Menu z-index; use a lower value (e.g. 40) for page-level selects, higher (e.g. 110) inside modals */
  menuZIndex?: number;
}

const MENU_MAX_HEIGHT = 320;

type MenuStyle = {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
  transform?: string;
};

export function ThemedSelect({
  id,
  value,
  onChange,
  options,
  placeholder = 'Select…',
  disabled = false,
  className = '',
  menuZIndex = 40,
}: ThemedSelectProps) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<MenuStyle | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = options.find((o) => o.value === value);

  const updateMenuPosition = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const gap = 8;
    const spaceBelow = window.innerHeight - rect.bottom - gap;
    const spaceAbove = rect.top - gap;
    const openUp = spaceBelow < 200 && spaceAbove > spaceBelow;

    if (openUp) {
      setMenuStyle({
        top: rect.top - gap,
        left: rect.left,
        width: rect.width,
        maxHeight: Math.max(120, Math.min(MENU_MAX_HEIGHT, spaceAbove)),
        transform: 'translateY(-100%)',
      });
    } else {
      setMenuStyle({
        top: rect.bottom + gap,
        left: rect.left,
        width: rect.width,
        maxHeight: Math.max(120, Math.min(MENU_MAX_HEIGHT, spaceBelow)),
      });
    }
  };

  useLayoutEffect(() => {
    if (!open) {
      setMenuStyle(null);
      return;
    }
    updateMenuPosition();

    const onScroll = (e: Event) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      updateMenuPosition();
    };

    window.addEventListener('resize', updateMenuPosition);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('resize', updateMenuPosition);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [open]);

  useEffect(() => {
    if (document.body.dataset.adminModalOpen === 'true') {
      setOpen(false);
    }
    const observer = new MutationObserver(() => {
      if (document.body.dataset.adminModalOpen === 'true') setOpen(false);
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ['data-admin-modal-open'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEscape);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEscape);
    };
  }, []);

  const menu =
    open && menuStyle
      ? createPortal(
          <AnimatePresence>
            <motion.ul
              ref={menuRef}
              role="listbox"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="themed-select-menu fixed overflow-y-scroll overscroll-contain rounded-xl py-1.5"
              style={{
                top: menuStyle.top,
                left: menuStyle.left,
                width: menuStyle.width,
                maxHeight: menuStyle.maxHeight,
                transform: menuStyle.transform,
                zIndex: menuZIndex,
              }}
              onWheel={(e) => e.stopPropagation()}
              onTouchMove={(e) => e.stopPropagation()}
            >
              {options.map((opt) => {
                const active = opt.value === value;
                return (
                  <li key={opt.value} role="option" aria-selected={active}>
                    <button
                      type="button"
                      className={`w-full text-left px-3 py-2.5 text-sm transition-colors ${
                        active
                          ? 'bg-cyan/15 text-cyan font-medium border-l-2 border-cyan'
                          : 'text-light/90 hover:bg-cyan/10 hover:text-cyan border-l-2 border-transparent'
                      }`}
                      onClick={() => {
                        onChange(opt.value);
                        setOpen(false);
                      }}
                    >
                      {opt.label}
                    </button>
                  </li>
                );
              })}
            </motion.ul>
          </AnimatePresence>,
          document.body,
        )
      : null;

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="themed-select-trigger ai-input w-full rounded-xl px-3 py-2.5 text-sm text-light flex items-center justify-between gap-2 text-left disabled:opacity-50 disabled:cursor-not-allowed"
        onClick={() => {
          if (disabled) return;
          setOpen((o) => !o);
        }}
      >
        <span className="truncate">{selected?.label ?? placeholder}</span>
        <ChevronDown
          size={18}
          className={`text-cyan shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {menu}
    </div>
  );
}

