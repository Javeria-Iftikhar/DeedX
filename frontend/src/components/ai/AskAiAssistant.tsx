import { motion } from 'framer-motion';
import { MessageCircle, Sparkles } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

export function AskAiAssistant() {
  const location = useLocation();
  const navigate = useNavigate();

  if (location.pathname === '/analytics') {
    return null;
  }

  return (
    <motion.button
      type="button"
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      onClick={() => navigate('/analytics')}
      className="fixed bottom-6 right-6 z-[200] flex items-center gap-2.5 pl-4 pr-5 py-3.5 rounded-full bg-gradient-to-r from-cyan/90 to-royal/90 text-[#050816] font-semibold text-sm shadow-[0_8px_32px_rgba(34,211,238,0.45),0_0_0_1px_rgba(255,255,255,0.15)_inset] border border-cyan/40"
      aria-label="Open Fiscal Analytics"
    >
      <MessageCircle size={20} />
      <span>Ask AI</span>
      <Sparkles size={16} className="opacity-90" />
    </motion.button>
  );
}
