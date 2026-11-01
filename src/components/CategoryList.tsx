import {useEffect, useRef, type CSSProperties} from 'react';
import {type Category} from '../types';
import {useMediaQuery} from '../store/useMediaQuery';
import {FoodImage} from './FoodImage';
import './CategoryList.css';

interface CategoryListProps {
  categories: {name: Category; image: string}[];
  category: Category;
  setCategory: (category: Category) => void;
}

export function CategoryList({categories, category, setCategory}: CategoryListProps) {
  const railRef = useRef<HTMLDivElement>(null);
  const mobileLayout = useMediaQuery('(max-width: 760px)');
  const displayedCategories = [...categories];
  if (mobileLayout) {
    const sidesIndex = displayedCategories.findIndex(item => item.name === 'Accompagnements');
    const drinksIndex = displayedCategories.findIndex(item => item.name === 'Boissons');
    if (sidesIndex >= 0 && drinksIndex >= 0) {
      [displayedCategories[sidesIndex], displayedCategories[drinksIndex]] =
        [displayedCategories[drinksIndex], displayedCategories[sidesIndex]];
    }
  }
  const categoryCount = Math.max(categories.length, 1);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail || rail.scrollWidth <= rail.clientWidth) return;
    const active = rail.querySelector<HTMLButtonElement>('[aria-pressed="true"]');
    if (!active) return;

    const viewport = rail.getBoundingClientRect();
    const target = active.getBoundingClientRect();
    const padding = 4;
    // Move this rail alone; scrollIntoView would also move the page vertically.
    if (target.left < viewport.left + padding) {
      rail.scrollTo({left: rail.scrollLeft + target.left - viewport.left - padding});
    } else if (target.right > viewport.right - padding) {
      rail.scrollTo({left: rail.scrollLeft + target.right - viewport.right + padding});
    }
  }, [category, categories.length, mobileLayout]);

  return (
    <div
      ref={railRef}
      className="categories category-strip"
      role="group"
      aria-label="Catégories"
      style={{
        '--category-columns': Math.min(categoryCount, 7),
        '--category-visible-count': Math.min(categoryCount, 5),
      } as CSSProperties}
    >
      {displayedCategories.map(item => (
        <button
          type="button"
          className={`category${category === item.name ? ' active' : ''}${item.name.length > 12 ? ' long-name' : ''}`}
          aria-pressed={category === item.name}
          key={item.name}
          onClick={() => setCategory(item.name)}
        >
          <span className="category-image"><FoodImage image={item.image}/></span>
          <span className="category-label">{item.name}</span>
          {category === item.name && <i/>}
        </button>
      ))}
    </div>
  );
}
