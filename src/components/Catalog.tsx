import {Search,SlidersHorizontal} from 'lucide-react';
import './SearchBar.css';
export {ProductCard} from './ProductCard';
export {PromoCarousel} from './PromoCarousel';
export {CategoryList} from './CategoryList';
export function SearchBar({query,setQuery,filters,setFilters}:{query:string;setQuery:(v:string)=>void;filters:boolean;setFilters:(v:boolean)=>void}){return <div className="search-wrap"><Search size={20}/><input aria-label="Rechercher un plat" placeholder="Rechercher votre plat préféré…" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button aria-label="Effacer la recherche" onClick={()=>setQuery('')}>×</button>}<button className={filters?'filter-button selected':'filter-button'} aria-label="Afficher les filtres" aria-expanded={filters} onClick={()=>setFilters(!filters)}><SlidersHorizontal size={19}/><span>Filtres</span></button></div>}
