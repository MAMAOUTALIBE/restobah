import {useMediaQuery} from './store/useMediaQuery';
import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowRight,MapPin,Clock,Leaf,Heart,Check,ChefHat,ShoppingBag} from 'lucide-react';
import {Footer} from './components/Footer';
import {Header,BottomNavigation,type View} from './components/Navigation';
import {SearchBar,PromoCarousel,CategoryList,ProductCard} from './components/Catalog';
import {ProductDetails} from './components/ProductDetails';
import {OfferBanner} from './components/OfferBanner';
import {Cart,basketSignature} from './components/Cart';
import {Account} from './components/Account';
import {Orders} from './components/Orders';
import {useCart,usePersisted} from './store/useCart';
import {useFavorites,useSession} from './store/useSession';
import {restaurantApi,messageOf} from './services/api';
import {categoryImages} from './data/products';
import type {Product,Category,CategoryInfo,Order,GuestOrderRef,RestaurantSettings} from './types';
import './features.css';

const validReferences=(value:unknown):value is GuestOrderRef[]=>Array.isArray(value)&&value.length<=100&&value.every(v=>v&&typeof v==='object'&&typeof v.id==='string'&&typeof v.accessToken==='string');
// Accent- and case-insensitive search: « epicee » finds « épicée ».
const searchable=(text:string)=>text.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLocaleLowerCase('fr').trim();
/** Guest tracking links from confirmation e-mails: keep the reference locally, then drop the token from the address bar. */
function linkedReference():GuestOrderRef|null{
  const params=new URLSearchParams(window.location.search);const id=params.get('order_id');const accessToken=params.get('token');
  if(!id||!accessToken)return null;
  params.delete('token');window.history.replaceState({},'',`${window.location.pathname}${params.toString()?`?${params}`:''}`);
  return {id,accessToken};
}
function initialView():View{const params=new URLSearchParams(window.location.search);return params.has('reset_uid')?'Compte':params.has('payment')||params.has('order_id')?'Commandes':'Accueil';}
export default function App(){
  const [view,setView]=useState<View>(initialView);
  // Stripe return marker, read once; the address bar is cleaned so the notice does not stick.
  const [paymentReturn]=useState(()=>new URLSearchParams(window.location.search).get('payment'));
  useEffect(()=>{const params=new URLSearchParams(window.location.search);if(!params.has('payment'))return;params.delete('payment');params.delete('order');window.history.replaceState({},'',`${window.location.pathname}${params.toString()?`?${params}`:''}`);},[]);
  const [query,setQuery]=useState('');
  const [category,setCategory]=useState<Category>('Tout');
  const [filters,setFilters]=useState(false);
  const [veggie,setVeggie]=useState(false);
  const [sort,setSort]=useState('popular');
  const [products,setProducts]=useState<Product[]>([]);
  const [categoryInfo,setCategoryInfo]=useState<CategoryInfo[]>([]);
  const [settings,setSettings]=useState<RestaurantSettings|null>(null);
  const [loading,setLoading]=useState(true);
  const [loadError,setLoadError]=useState('');
  const [selected,setSelected]=useState<Product|null>(null);
  const [cartOpen,setCartOpen]=useState(false);
  const [references,setReferences]=usePersisted<GuestOrderRef[]>('stc-guest-orders',[],validReferences);
  useEffect(()=>{const linked=linkedReference();if(linked)setReferences(old=>[linked,...old.filter(r=>r.id!==linked.id)].slice(0,50));},[setReferences]);
  const [toast,setToast]=useState<{message:string;showCart:boolean}|null>(null);
  const cart=useCart();
  const session=useSession();
  const favorites=useFavorites(session.user);
  const cartRef=useRef(cart);
  useEffect(()=>{cartRef.current=cart;},[cart]);
  const closeProduct=useCallback(()=>setSelected(null),[]);
  const closeCart=useCallback(()=>setCartOpen(false),[]);
  const reconcile=cart.reconcile;
  const loadGeneration=useRef(0);
  const restaurantActive=useRef(false);
  const restaurantRequest=useRef<Promise<RestaurantSettings>|null>(null);
  // Polling and checkout share one settings source. A confirmation gets a new
  // read after any older polling request, so its result cannot be overwritten.
  const refreshRestaurant=useCallback(function readRestaurant(fresh=false):Promise<RestaurantSettings>{
    const running=restaurantRequest.current;
    if(running){
      if(!fresh)return running;
      return running.catch(()=>undefined).then(()=>readRestaurant(true));
    }
    if(!restaurantActive.current)return Promise.reject(new Error('La page a changé. Rouvrez votre panier pour réessayer.'));
    const request:Promise<RestaurantSettings>=restaurantApi.getRestaurant().then(restaurant=>{
      if(!restaurantActive.current)throw new Error('La page a changé. Rouvrez votre panier pour réessayer.');
      setSettings(restaurant);
      return restaurant;
    }).finally(()=>{if(restaurantRequest.current===request)restaurantRequest.current=null;});
    restaurantRequest.current=request;
    return request;
  },[]);
  const refreshCheckoutSettings=useCallback(()=>refreshRestaurant(true),[refreshRestaurant]);
  const load=useCallback(async()=>{
    const generation=++loadGeneration.current;
    setLoading(true);setLoadError('');
    try{
      const [catalog,,list]=await Promise.all([restaurantApi.getProducts(),refreshRestaurant(),restaurantApi.getCategories().catch(()=>[] as CategoryInfo[])]);
      if(generation!==loadGeneration.current)return;
      setProducts(catalog);setCategoryInfo(list);reconcile(catalog);
    }catch(error){if(generation===loadGeneration.current)setLoadError(messageOf(error));}
    finally{if(generation===loadGeneration.current)setLoading(false);}
  },[reconcile,refreshRestaurant]);
  useEffect(()=>{restaurantActive.current=true;void load();try{localStorage.removeItem('smash-orders');}catch{/* old simulated history is no longer authoritative */}return()=>{restaurantActive.current=false;loadGeneration.current++;};},[load]);
  useEffect(()=>{if(toast){const timer=window.setTimeout(()=>setToast(null),4500);return()=>window.clearTimeout(timer);}},[toast]);
  useEffect(()=>{
    if(loading)return;
    let stopped=false;
    let inFlight=false;
    const refresh=async()=>{
      if(stopped||inFlight||document.visibilityState!=='visible')return;
      inFlight=true;
      try{
        const [catalog,,list]=await Promise.allSettled([
          restaurantApi.getProducts(),refreshRestaurant(),restaurantApi.getCategories(),
        ]);
        if(stopped)return;
        if(catalog.status==='fulfilled'){
          setProducts(catalog.value);reconcile(catalog.value);setLoadError('');
          setSelected(current=>current
            ?catalog.value.find(product=>product.id===current.id)??{...current,available:false}
            :null);
        }
        if(list.status==='fulfilled')setCategoryInfo(list.value);
      }finally{inFlight=false;}
    };
    const resume=()=>{void refresh();};
    const timer=window.setInterval(resume,15000);
    window.addEventListener('focus',resume);
    document.addEventListener('visibilitychange',resume);
    return()=>{
      stopped=true;window.clearInterval(timer);
      window.removeEventListener('focus',resume);
      document.removeEventListener('visibilitychange',resume);
    };
  },[loading,reconcile,refreshRestaurant]);
  const navigate=useCallback((next:View)=>{
    if(next==='Panier'){setCartOpen(true);return;}
    setView(next);
    if(next==='Accueil'||next==='Carte'){setQuery('');setCategory('Tout');setVeggie(false);}
    window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  },[]);
  const registered=useCallback((order:Order)=>{
    if(!session.user&&order.accessToken)setReferences(old=>[{id:order.id,accessToken:order.accessToken!},...old.filter(r=>r.id!==order.id)].slice(0,50));
  },[session.user,setReferences]);
  const onPaid=useCallback((order:Order)=>{
    try{const saved=JSON.parse(sessionStorage.getItem('stc-payment-cart')||'null') as {id?:string;signature?:string}|null;if(saved?.id===order.id){if(saved.signature===basketSignature(cartRef.current))cartRef.current.clear();sessionStorage.removeItem('stc-payment-cart');sessionStorage.removeItem('stc-checkout-key');}}catch{/* local storage is optional */}
  },[]);
  const regular=products.filter(p=>!p.promotional);
  // Administration order first; a category is listed only when it has dishes.
  const categoryNames=[...new Set([...[...categoryInfo].sort((a,b)=>a.position-b.position).map(c=>c.name),...regular.map(p=>p.category)])].filter(name=>regular.some(p=>p.category===name));
  const categoryList=[{name:'Tout',image:categoryImages.Tout},...categoryNames.map(name=>({name,image:categoryImages[name]??regular.find(p=>p.category===name)!.image}))];
  const terms=searchable(query);
  const filtered=regular.filter(p=>(category==='Tout'||p.category===category)&&(!veggie||p.vegetarian)&&(view!=='Favoris'||favorites.ids.includes(p.id))&&searchable(`${p.name} ${p.summary||''} ${p.description} ${p.category}`).includes(terms)).sort((a,b)=>sort==='price'?a.price-b.price:sort==='price-desc'?b.price-a.price:0);
  const home=view==='Accueil'&&!query&&category==='Tout';
  const mobileLayout=useMediaQuery('(max-width: 760px)');
  const tabletLayout=useMediaQuery('(max-width: 1100px)');
  const homeLimit=mobileLayout?3:tabletLayout?6:4;
  const shown=home&&!veggie?filtered.slice(0,homeLimit):filtered;
  return <>
    <Header count={cart.count} onNavigate={navigate} view={view} settings={settings}/>
    <main className={home?'home-view':''}>
      <div className="topline"><p><MapPin size={15}/><strong>{settings?.city||'STC'}</strong><span className="dot-separator">·</span> Votre nouvelle bonne adresse</p>{settings?.pickupDelay&&<span><Clock size={14}/> À emporter en {settings.pickupDelay}</span>}</div>
      {settings&&!settings.orderingEnabled||settings&&!settings.isOpen?<p className="notice" role="status">Le restaurant est actuellement fermé aux commandes. Vous pouvez consulter la carte et préparer votre panier.</p>:null}
      {(['Accueil','Carte','Favoris'] as View[]).includes(view)?<>
        <div className="welcome-row"><div><span className="small-label">DU BON, DU FRAIS, DU FAIT MAISON.</span><h2>{view==='Favoris'?'Vos coups de cœur.':<>Une petite faim<span className="red"> ?</span></>}</h2></div><SearchBar query={query} setQuery={setQuery} filters={filters} setFilters={setFilters}/></div>
        {favorites.error&&<div className="notice error" role="alert">{favorites.error}<button className="text-button" onClick={favorites.retry}>Réessayer la synchronisation</button></div>}
        {filters&&<div className="filters"><label><input type="checkbox" checked={veggie} onChange={e=>setVeggie(e.target.checked)}/><Leaf size={16}/>Végétarien</label><label>Trier par<select aria-label="Trier les produits" value={sort} onChange={e=>setSort(e.target.value)}><option value="popular">Nos préférés</option><option value="price">Prix croissant</option><option value="price-desc">Prix décroissant</option></select></label><button onClick={()=>{setVeggie(false);setSort('popular');}}>Réinitialiser</button></div>}
        {view==='Accueil'&&!query&&<PromoCarousel products={products} onOrder={id=>{const product=products.find(p=>p.id===id);if(product)setSelected(product);else if(!loading)setToast({message:'La carte n’est pas accessible. Veuillez réessayer.',showCart:false});}}/>}
        <CategoryList categories={categoryList} category={category} setCategory={setCategory}/>
        <section className="catalog-section" id="carte"><div className="section-heading"><div><span className="small-label">{view==='Favoris'?'À RETROUVER QUAND VOUS VOULEZ':'À PARTAGER OU À GARDER POUR SOI'}</span><h2>{query?`Résultats pour « ${query} »`:view==='Favoris'?'Mes favoris':category!=='Tout'?category:view==='Carte'?'À la carte':'Nos menus populaires'}<span className="heading-star">✳</span></h2></div><button className="text-button" onClick={()=>navigate('Carte')}>Voir tout <ArrowRight size={17}/></button></div>
          {loading?<div className="product-grid" aria-label="Chargement des plats" aria-busy="true">{[1,2,3].map(n=><div className="skeleton" key={n}/>)}</div>:loadError?<div className="empty" role="alert"><h3>La carte n’a pas pu être chargée.</h3><p>{loadError}</p><button className="primary" onClick={()=>void load()}>Réessayer</button></div>:shown.length?<div className="product-grid">{shown.map(product=><ProductCard key={product.id} product={product} largeImage={product.id===1} favorite={favorites.ids.includes(product.id)} onFavorite={()=>favorites.toggle(product.id)} onOpen={()=>setSelected(product)}/>)}</div>:<div className="empty"><Heart size={35}/><h3>{view==='Favoris'?'Vos futurs favoris sont à la carte.':'Aucun plat pour cette recherche.'}</h3><p>{view==='Favoris'?'Touchez le cœur d’un plat pour le retrouver ici.':'Essayez un autre mot ou une autre catégorie.'}</p><button className="primary" onClick={()=>navigate('Carte')}>Voir tous les plats</button></div>}
        </section>
        {(view==='Accueil'||view==='Carte')&&!query&&!loading&&!loadError&&<OfferBanner products={products} filteredProducts={filtered} category={category} vegetarian={veggie} onOrder={setSelected}/>}
        {view==='Accueil'&&!query&&!loading&&!loadError&&<div className="values"><span><ChefHat/><span><strong>Cuisiné sur place</strong><small>Du fait maison, chaque jour.</small></span></span><span><Leaf/><span><strong>Des ingrédients choisis</strong><small>Le bon goût commence ici.</small></span></span><span><ShoppingBag/><span><strong>À votre rythme</strong><small>À emporter ou livré chez vous.</small></span></span></div>}
      </>:view==='Commandes'?<Orders key={session.user?.id??'guest'} user={session.user} references={references} paymentReturn={paymentReturn} onBrowse={()=>navigate('Carte')} onPaid={onPaid}/>:<Account key={session.user?.id??'guest'} session={session} onNavigate={navigate} favoriteCount={favorites.ids.length} onDeleted={message=>setToast({message,showCart:false})}/>}
    </main>
    <Footer onNavigate={navigate} settings={settings}/>
    <BottomNavigation view={cartOpen?'Panier':view} count={cart.count} onNavigate={navigate}/>
    {selected&&<ProductDetails key={selected.id} product={selected} onClose={closeProduct} onAdd={item=>{cart.add(item);setToast({message:`${item.product.name} ajouté au panier`,showCart:true});}}/>}
    {cartOpen&&<Cart cart={cart} settings={session.loading?null:settings} refreshSettings={refreshCheckoutSettings} user={session.user} onClose={closeCart} onRegistered={registered} onComplete={order=>{setCartOpen(false);setSelected(null);setView('Commandes');setToast({message:order.demoMode?'Commande de démonstration confirmée !':order.paymentMethod==='on_site'?`Commande confirmée · À régler ${order.mode==='Livraison'?'à la livraison':'au restaurant'}`:'Commande enregistrée !',showCart:false});window.scrollTo(0,0);}}/>}
    {toast&&<div className="toast" role="status"><Check size={18}/>{toast.message}{toast.showCart&&<button onClick={()=>{setCartOpen(true);setToast(null);}}>Voir le panier</button>}<button aria-label="Fermer la notification" onClick={()=>setToast(null)}>×</button></div>}
  </>;
}
