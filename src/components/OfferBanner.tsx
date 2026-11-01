import {ArrowRight} from 'lucide-react';
import {euro, type Category, type Product} from '../types';
import {FoodImage} from './FoodImage';
import './OfferBanner.css';

interface OfferBannerProps {
  products: Product[];
  filteredProducts: Product[];
  category: Category;
  vegetarian: boolean;
  onOrder: (product: Product) => void;
}

function discountOf(product: Product) {
  return product.promotional ? Math.max(0, product.discountPercent ?? 0) : 0;
}

export function selectOfferProduct({
  products, filteredProducts, category, vegetarian,
}: Pick<OfferBannerProps, 'products' | 'filteredProducts' | 'category' | 'vegetarian'>) {
  const eligible = (product: Product) => product.available !== false
    && (category === 'Tout' || product.category === category)
    && (!vegetarian || product.vegetarian === true);

  // Keep catalogue order when two promotions share the same discount.
  let promotion: Product | undefined;
  for (const product of products) {
    if (discountOf(product) > 0 && eligible(product)
      && (!promotion || discountOf(product) > discountOf(promotion))) {
      promotion = product;
    }
  }
  return promotion ?? filteredProducts.find(product => !product.promotional && eligible(product));
}

export function OfferBanner(props: OfferBannerProps) {
  const product = selectOfferProduct(props);
  if (!product) return null;

  const discount = discountOf(product);
  const discounted = discount > 0;
  // Retain the original composition only for the menu pictured in that artwork.
  const originalArt = discounted && props.category === 'Tout' && product.image === 'stc-menu-2';

  return (
    <section
      className={`offer category-offer ${originalArt ? 'category-offer--art' : 'category-offer--product'} ${discounted ? 'category-offer--promotion' : 'category-offer--selection'}`}
      aria-label={`${discounted ? 'Offre' : 'Notre sélection'} : ${product.name}`}
    >
      <FoodImage
        className="offer-food"
        image={originalArt ? 'stc-offer-violet' : product.image}
        alt={product.name}
      />
      <div className="category-offer-copy">
        <span className="small-label">{discounted ? 'L’OFFRE DU MOMENT' : 'NOTRE SÉLECTION'}</span>
        <h2>{discounted ? `Jusqu’à −${discount} %` : product.name}</h2>
        <p>{discounted ? originalArt ? 'Sur une sélection de menus.' : product.name : euro(product.price)}</p>
      </div>
      <button
        type="button"
        className="primary"
        aria-label={`Commander ${product.name}`}
        onClick={() => props.onOrder(product)}
      >
        Commander <ArrowRight size={17} aria-hidden="true"/>
      </button>
      {discounted && (
        <span className="offer-discount" aria-label={`${discount} % de remise`}>
          {discount}<small>%</small><b>DE REMISE</b>
        </span>
      )}
    </section>
  );
}
