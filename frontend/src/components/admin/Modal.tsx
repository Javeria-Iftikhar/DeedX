import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ open, title, onClose, children }: ModalProps) {
  useEffect(() => {
    if (open) {
      document.body.dataset.adminModalOpen = 'true';
      return () => {
        delete document.body.dataset.adminModalOpen;
      };
    }
    return undefined;
  }, [open]);

  if (!open) return null;

  return createPortal(
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="neon-card rounded-2xl border-glow w-full max-w-lg max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between shrink-0 px-6 pt-6 pb-2">
          <h3 className="text-lg font-semibold text-light font-[family-name:var(--font-display)]">{title}</h3>
          <button type="button" onClick={onClose} className="text-slate hover:text-light text-xl leading-none">&times;</button>
        </div>
        <div className="overflow-y-auto overflow-x-visible px-6 pb-6 flex-1 min-h-0">
          {children}
        </div>
      </motion.div>
    </motion.div>,
    document.body,
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-3">
      <label className="text-xs uppercase tracking-wider text-slate block mb-1.5">{label}</label>
      {children}
    </div>
  );
}

export const inputClass = 'ai-input w-full rounded-xl px-3 py-2.5 text-sm text-light';
