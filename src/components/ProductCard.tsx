import {ArrowUpRight, Heart, Plus} from 'lucide-react';
import {euro, type OptionGroup, type Product} from '../types';
import {FoodImage} from './FoodImage';
import './ProductCard.css';

interface ProductCardProps {
  product: Product;
  favorite: boolean;
  largeImage?: boolean;
  onFavorite: () => void;
  onOpen: () => void;
}

function optionLabel(group: OptionGroup) {
  if (group.min === 0) return 'Suppléments';
  const name = group.name.replace(/^(votre|vos)\s+/i, '');
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} au choix`;
}

export function ProductCard({product, favorite, largeImage = false, onFavorite, onOpen}: ProductCardProps) {
  const formula = product.category === 'Menus';
  const burger = product.category === 'Burgers';
  const menuStyle = ['Menus', 'Burgers', 'Poulet', 'Accompagnements'].includes(product.category);
  // Highlight only products already identified as a specialty by the catalogue.
  const specialty = !formula && /^(best[ -]?seller|populaire|incontournable)/i.test(product.badge || '');
  const unavailable = product.available === false;
  const variant = formula ? 'formula-card' : specialty ? 'specialty-card' : 'dish-card';
  const options = formula
    ? [...new Set((product.optionGroups || []).filter(group => group.choices.length).map(optionLabel))]
    : [];
  const vegetarianBadge = burger && product.vegetarian && !product.badge;
  const badge = product.badge || (formula ? 'Menu complet' : vegetarianBadge ? 'Végétarien' : undefined);
  // These bundled portraits leave a large part of the frame to their background.
  const portraitImage = (burger && product.image === 'spicy')
    || (product.category === 'Accompagnements' && product.image === 'fries');

  return (
    <article className={`product-card ${variant}${menuStyle ? ' menu-style-card' : ''}${largeImage ? ' large-image-card' : ''}${unavailable ? ' unavailable' : ''}`}>
      <button
        type="button"
        className={`card-media${portraitImage ? ' card-media--portrait' : ''}`}
        onClick={onOpen}
        aria-label={`Personnaliser ${product.name}`}
      >
        <FoodImage image={product.image} alt={product.name}/>
      </button>
      <button
        type="button"
        className={`card-favorite${favorite ? ' is-favorite' : ''}`}
        aria-label={`${favorite ? 'Retirer' : 'Ajouter'} ${product.name} ${favorite ? 'des' : 'aux'} favoris`}
        aria-pressed={favorite}
        onClick={onFavorite}
      >
        <Heart size={19} strokeWidth={1.8} fill={favorite ? 'currentColor' : 'none'}/>
      </button>

      <div className="card-body">
        {badge && <span className={`card-badge${vegetarianBadge ? ' card-badge--vegetarian' : ''}`}>{badge}</span>}
        {menuStyle && !badge && <span className="card-badge-spacer" aria-hidden="true"/>}
        <h3 className="card-title">
          <button type="button" onClick={onOpen}>{product.name}</button>
        </h3>
        <p className="card-text">
          {unavailable ? 'Temporairement indisponible' : product.summary || product.description}
        </p>
        {options.length > 0 && (
          <ul className="card-options" aria-label="Options du menu">
            {options.map(option => <li key={option}>{option}</li>)}
          </ul>
        )}

        <div className="card-footer">
          <strong className="card-price">{euro(product.price)}</strong>
          {formula ? (
            <button
              type="button"
              className="card-choose"
              aria-label={`Choisir ${product.name}`}
              disabled={unavailable}
              onClick={onOpen}
            >
              Choisir <ArrowUpRight size={15} aria-hidden="true"/>
            </button>
          ) : (
            <button
              type="button"
              className="card-add"
              aria-label={`Ajouter ${product.name}`}
              disabled={unavailable}
              onClick={onOpen}
            >
              <Plus size={25} strokeWidth={1.8} aria-hidden="true"/>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
