import { motion } from 'framer-motion';

// const LOGO_SRC = '/logo.png'; chneg to below

const LOGO_SRC = `${import.meta.env.BASE_URL}logo.png`;

interface LogoProps {
  /** full = navbar/sidebar | lead = hero intro | icon = sidebar collapsed | hero = large accent */
  variant?: 'full' | 'lead' | 'icon' | 'hero';
  className?: string;
}

const sizes = {
  full: 'h-8 sm:h-9 w-auto',
  lead: 'h-16 sm:h-[4.5rem] md:h-20 lg:h-[7rem] w-auto max-w-[min(100%,22rem)]',
  hero: 'h-14 sm:h-16 md:h-20 lg:h-24 w-auto',
  icon: 'h-10 w-10',
};

export function Logo({ variant = 'full', className = '' }: LogoProps) {
  if (variant === 'icon') {
    return (
      <motion.div className={`overflow-hidden shrink-0 ${sizes.icon} ${className}`} aria-label="Fiscala">
        <img src={LOGO_SRC} alt="Fiscala" className="h-full w-auto max-w-none object-left object-contain" />
      </motion.div>
    );
  }

  const sizeClass =
    variant === 'hero' ? sizes.hero : variant === 'lead' ? sizes.lead : sizes.full;

  return (
    <motion.img
      src={LOGO_SRC}
      alt="Fiscala"
      className={`object-contain ${sizeClass} ${
        variant === 'hero' || variant === 'lead'
          ? 'drop-shadow-[0_0_32px_rgba(34,211,238,0.2)]'
          : ''
      } ${className}`}
    />
  );
}
