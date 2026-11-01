import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Bell, Menu, ShoppingBag, X} from 'lucide-react';
import {MobileMenu} from '../src/components/MobileMenu';
import type {View} from '../src/components/Navigation';
import './mobile-menu-preview.css';

type ProposalVariant = 'cream' | 'grid' | 'violet';

const proposals: {variant: ProposalVariant; name: string; caption: string; recommended?: boolean}[] = [
  {variant: 'cream', name: 'Liste crème', caption: 'Des liens clairs, une page active bien visible.', recommended: true},
  {variant: 'grid', name: 'Grille de raccourcis', caption: 'Une navigation en tuiles, plus visuelle.'},
  {variant: 'violet', name: 'Panneau violet', caption: 'Un contraste plus affirmé.'},
];

function Proposal({variant, name, caption, recommended, index}: typeof proposals[number] & {index: number}) {
  const [view, setView] = useState<View>('Accueil');
  const [open, setOpen] = useState(true);

  return (
    <article className="proposal" data-design={variant} aria-label={name}>
      <div className="proposal-heading">
        <span className="proposal-number">0{index + 1}</span>
        <h2>{name}</h2>
        {recommended && <span className="proposal-recommended">Conseillé</span>}
      </div>
      <div className="proposal-phone">
        <div className="proposal-header">
          <button
            type="button"
            className="proposal-header-control"
            aria-label={open ? 'Fermer cet aperçu du menu' : 'Ouvrir cet aperçu du menu'}
            aria-expanded={open}
            aria-controls={`proposal-menu-${variant}`}
            onClick={() => setOpen(!open)}
          >
            {open ? <X size={21} aria-hidden="true"/> : <Menu size={21} aria-hidden="true"/>}
          </button>
          <strong className="proposal-logo">STC</strong>
          <span className="proposal-header-control proposal-header-decoration" aria-hidden="true"><Bell size={21}/></span>
          <span className="proposal-header-control proposal-header-decoration" aria-hidden="true"><ShoppingBag size={21}/></span>
        </div>
        {open ? (
          <MobileMenu id={`proposal-menu-${variant}`} view={view} onNavigate={setView} onClose={() => undefined} variant={variant}/>
        ) : (
          <button type="button" className="proposal-reopen" onClick={() => setOpen(true)}>Ouvrir le menu</button>
        )}
      </div>
      <p className="proposal-caption">{caption}</p>
    </article>
  );
}

function MenuProposals() {
  return (
    <main className="menu-proposals">
      <div className="proposals-intro">
        <span>STC · MENU MOBILE</span>
        <h1>Trois façons de naviguer.</h1>
      </div>
      <div className="proposals-grid">
        {proposals.map((proposal, index) => <Proposal key={proposal.variant} {...proposal} index={index}/>)}
      </div>
    </main>
  );
}

const root = document.getElementById('menu-proposals-root');
if (root) createRoot(root).render(<MenuProposals/>);
