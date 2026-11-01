import {Menu,ShoppingBag,Home,LayoutGrid,ReceiptText,User,Heart,X,Bell} from 'lucide-react';
import {useCallback,useEffect,useRef,useState} from 'react';
import type {RestaurantSettings} from '../types';
import {MobileMenu} from './MobileMenu';
export type View='Accueil'|'Carte'|'Panier'|'Commandes'|'Compte'|'Favoris';

export function Header({count,onNavigate,view,settings}:{count:number;onNavigate:(v:View)=>void;view:View;settings:RestaurantSettings|null}) {
  const [menu,setMenu]=useState(false);
  const headerRef=useRef<HTMLElement>(null);
  const toggleRef=useRef<HTMLButtonElement>(null);
  const panelRef=useRef<HTMLDivElement>(null);
  const closeMenu=useCallback(()=>setMenu(false),[]);

  useEffect(()=>{closeMenu();},[view,closeMenu]);

  useEffect(()=>{
    if(!menu)return;
    const desktop=window.matchMedia('(min-width: 761px)');
    const updateHeight=()=>{
      if(desktop.matches){closeMenu();return;}
      const headerBottom=headerRef.current?.getBoundingClientRect().bottom;
      if(headerBottom===undefined)return;
      const viewportHeight=window.visualViewport?.height??window.innerHeight;
      panelRef.current?.style.setProperty('--mobile-menu-max-height',`${Math.max(0,viewportHeight-headerBottom-18)}px`);
    };
    const outside=(target:EventTarget|null)=>target instanceof Node
      && !panelRef.current?.contains(target) && !toggleRef.current?.contains(target);
    const pointerHandler=(event:PointerEvent)=>{if(outside(event.target))closeMenu();};
    const focusHandler=(event:FocusEvent)=>{if(outside(event.target))closeMenu();};
    const keyHandler=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){
        event.preventDefault();
        closeMenu();
        toggleRef.current?.focus({preventScroll:true});
      }
    };
    updateHeight();
    const current=panelRef.current?.querySelector<HTMLButtonElement>('button[aria-current="page"]')
      ??panelRef.current?.querySelector<HTMLButtonElement>('button');
    current?.focus({preventScroll:true});
    const panel=panelRef.current?.querySelector<HTMLElement>('.mobile-menu-panel');
    if(panel&&current){
      const overflow=current.getBoundingClientRect().bottom-panel.getBoundingClientRect().bottom+8;
      if(overflow>0)panel.scrollTop+=overflow;
    }
    const observer=new ResizeObserver(updateHeight);
    if(headerRef.current)observer.observe(headerRef.current);
    document.addEventListener('pointerdown',pointerHandler);
    document.addEventListener('focusin',focusHandler);
    document.addEventListener('keydown',keyHandler);
    window.addEventListener('resize',updateHeight);
    window.visualViewport?.addEventListener('resize',updateHeight);
    desktop.addEventListener('change',updateHeight);
    return()=>{
      observer.disconnect();
      document.removeEventListener('pointerdown',pointerHandler);
      document.removeEventListener('focusin',focusHandler);
      document.removeEventListener('keydown',keyHandler);
      window.removeEventListener('resize',updateHeight);
      window.visualViewport?.removeEventListener('resize',updateHeight);
      desktop.removeEventListener('change',updateHeight);
    };
  },[menu,closeMenu]);

  const navigate=(next:View)=>{closeMenu();onNavigate(next);};

  return (
    <header className="site-header" ref={headerRef}>
      <div className="header-inner">
        <button
          ref={toggleRef}
          type="button"
          className="icon-button mobile-menu"
          aria-label={menu?'Fermer le menu':'Ouvrir le menu'}
          aria-expanded={menu}
          aria-controls="mobile-menu"
          onClick={()=>setMenu(!menu)}
        >
          {menu?<X/>:<Menu/>}
        </button>
        <a className="brand" href="#" onClick={event=>{event.preventDefault();navigate('Accueil');}}>
          <strong className="stc-logo">{settings?.name||'STC'}</strong>
        </a>
        <nav className="desktop-nav" aria-label="Navigation ordinateur">
          {(['Accueil','Carte','Commandes'] as View[]).map(destination=>(
            <button
              className={view===destination?'active':''}
              aria-current={view===destination?'page':undefined}
              onClick={()=>navigate(destination)}
              key={destination}
            >
              {destination==='Carte'?'Notre carte':destination}
            </button>
          ))}
        </nav>
        <div className="header-right">
          <button className="icon-button notification-button" aria-label="Voir le suivi des commandes" onClick={()=>navigate('Commandes')}><Bell size={23}/></button>
          <span className={`open-status ${settings&&(!settings.isOpen||!settings.orderingEnabled)?'closed':''}`}><i/>{settings?settings.isOpen&&settings.orderingEnabled?'Commandes ouvertes':'Commandes fermées':'Connexion…'}</span>
          <button className="icon-button favorite-header" aria-label="Mes favoris" onClick={()=>navigate('Favoris')}><Heart size={20}/></button>
          <button className="icon-button account-header" aria-label="Mon compte" onClick={()=>navigate('Compte')}><User size={20}/></button>
          <button className="cart-button" aria-label={`Mon panier, ${count} articles`} onClick={()=>navigate('Panier')}><ShoppingBag size={18}/><span>Mon panier</span>{count>0&&<b>{count}</b>}</button>
        </div>
      </div>
      {menu&&<div className="mobile-menu-position" ref={panelRef}><MobileMenu view={view} onNavigate={onNavigate} onClose={closeMenu}/></div>}
    </header>
  );
}

export function BottomNavigation({view,count,onNavigate}:{view:View;count:number;onNavigate:(v:View)=>void}){return <nav className="bottom-nav" aria-label="Navigation principale">{([{name:'Accueil',icon:Home},{name:'Carte',icon:LayoutGrid},{name:'Panier',icon:ShoppingBag},{name:'Commandes',icon:ReceiptText},{name:'Compte',icon:User}] as const).map(({name,icon:Icon})=><button className={`${name==='Panier'?'nav-cart ':''}${view===name?'active':''}`} aria-current={view===name?'page':undefined} key={name} onClick={()=>onNavigate(name)}><span><Icon size={21}/>{name==='Panier'&&count>0&&<b>{count}</b>}</span>{name}</button>)}</nav>}
