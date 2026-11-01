import {ArrowRight} from 'lucide-react';
import {useState} from 'react';
import {type Product} from '../types';
import './PromoCarousel.css';

interface PromoCarouselProps {
  products: Product[];
  onOrder: (productId: number) => void;
}

const slides = [
  {title: ['Le goût', 'STC.'], productId: 1, image: 'stc-hero-violet', brand: true},
  {title: ['À', 'partager.'], productId: 3, image: 'stc-promo-tenders-violet', brand: false},
  {title: ['Menu', 'complet.'], productId: 2, image: 'stc-promo-menu-violet', brand: false},
];

export function PromoCarousel({products, onOrder}: PromoCarouselProps) {
  const [activeSlide, setActiveSlide] = useState(0);
  const slide = slides[activeSlide];
  const product = products.find(item => item.id === slide.productId);

  return (
    <section className="promo-banner" aria-roledescription="carrousel" aria-label="Nos promotions">
      <img
        className={`promo-visual${slide.brand ? '' : ' promo-visual--background'}`}
        src={`/images/${slide.image}.jpg`}
        alt={product?.name || ''}
      />
      <div className="promo-content">
        <h1 className={`promo-title${slide.brand ? ' promo-title--brand' : ''}`} aria-live="polite">
          <span>{slide.title[0]}</span>{' '}
          <span className="promo-title-accent">{slide.title[1]}</span>
        </h1>
        <button
          type="button"
          className="promo-order"
          onClick={() => onOrder(slide.productId)}
          disabled={!product || product.available === false}
        >
          Commander <ArrowRight size={18} aria-hidden="true"/>
        </button>
      </div>
      <div className="promo-pagination" role="group" aria-label="Choisir une promotion">
        {slides.map((_, index) => (
          <button
            key={index}
            type="button"
            className="promo-page"
            aria-label={`Promotion ${index + 1}`}
            aria-current={activeSlide === index ? 'true' : undefined}
            onClick={() => setActiveSlide(index)}
          >
            <span aria-hidden="true"/>
          </button>
        ))}
      </div>
    </section>
  );
}
