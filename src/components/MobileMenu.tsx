import {ChevronRight, Heart, Home, LayoutGrid, ReceiptText, User} from 'lucide-react';
import type {View} from './Navigation';
import './MobileMenu.css';

export type MobileMenuVariant = 'cream' | 'grid' | 'violet';

interface MobileMenuProps {
  view: View;
  onNavigate: (view: View) => void;
  onClose: () => void;
  variant?: MobileMenuVariant;
  id?: string;
  className?: string;
}

const destinations = [
  {name: 'Accueil', icon: Home},
  {name: 'Carte', icon: LayoutGrid},
  {name: 'Favoris', icon: Heart},
  {name: 'Commandes', icon: ReceiptText},
  {name: 'Compte', icon: User},
] as const;

export function MobileMenu({
  view, onNavigate, onClose, variant = 'cream', id = 'mobile-menu', className = '',
}: MobileMenuProps) {
  return (
    <nav
      id={id}
      className={`mobile-menu-panel mobile-menu-panel--${variant} ${className}`.trim()}
      aria-label="Menu mobile"
    >
      {destinations.map(({name, icon: Icon}) => (
        <button
          type="button"
          className="mobile-menu-item"
          key={name}
          aria-current={view === name ? 'page' : undefined}
          onClick={() => {onNavigate(name); onClose();}}
        >
          <span className="mobile-menu-item-icon"><Icon size={19} strokeWidth={1.8} aria-hidden="true"/></span>
          <span className="mobile-menu-item-label">{name}</span>
          <ChevronRight className="mobile-menu-item-chevron" size={15} aria-hidden="true"/>
        </button>
      ))}
    </nav>
  );
}
