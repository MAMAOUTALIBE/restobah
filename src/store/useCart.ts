import {useCallback,useEffect,useState} from 'react';
import {cents,type CartItem,type Product} from '../types';
export function readStorage<T>(key:string,fallback:T,validate?:(v:unknown)=>v is T):T{
  try{const value:unknown=JSON.parse(localStorage.getItem(key)||'null');return value!==null&&(!validate||validate(value))?value as T:fallback;}catch{return fallback;}
}
export function usePersisted<T>(key:string,fallback:T,validate?:(v:unknown)=>v is T){
  const [value,setValue]=useState<T>(()=>readStorage(key,fallback,validate));
  useEffect(()=>{try{localStorage.setItem(key,JSON.stringify(value));}catch{/* The in-memory session remains usable when storage is disabled. */}},[key,value]);
  return [value,setValue] as const;
}
const isRecord=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function readCart():CartItem[]{
  const saved=readStorage<unknown>('stc-cart-v2',null)??readStorage<unknown>('smash-cart',[]);
  if(!Array.isArray(saved))return [];
  return saved.slice(0,100).flatMap((v:unknown)=>{
    if(!isRecord(v)||!isRecord(v.product)||!Number.isInteger(v.product.id)||typeof v.product.name!=='string'||typeof v.quantity!=='number'||!Number.isFinite(v.quantity))return [];
    const p=v.product;
    if(typeof p.price!=='number'||!Number.isFinite(p.price)||p.price<0||typeof p.image!=='string')return [];
    const choices=Array.isArray(v.choices)?v.choices.filter((c):c is string=>typeof c==='string'):[];
    return [{key:typeof v.key==='string'?v.key:`${p.id}`,product:p as unknown as Product,quantity:Math.max(1,Math.min(20,Math.floor(v.quantity))),choices,choiceNames:Array.isArray(v.choiceNames)?v.choiceNames.filter((c):c is string=>typeof c==='string'):[],unitPrice:typeof v.unitPrice==='number'&&Number.isFinite(v.unitPrice)&&v.unitPrice>=0?v.unitPrice:p.price,option:typeof v.option==='string'?v.option:undefined,extras:Array.isArray(v.extras)?v.extras.filter((c):c is string=>typeof c==='string'):undefined,issue:'Vérification du panier en cours…'}];
  });
}
export const cartKey=(id:number,choices:string[])=>`${id}:${[...choices].sort().join('|')}`;
export function checkedItem(item:CartItem,products:Product[]):CartItem{
  const p=products.find(product=>product.id===item.product.id);
  if(!p)return {...item,issue:'Ce plat n’est plus à la carte. Supprimez-le pour continuer.'};
  const groups=p.optionGroups||[];
  const all=groups.flatMap(g=>g.choices);
  let selected=[...item.choices];
  if(!selected.length&&(item.option||item.extras?.length)){
    const required=groups.filter(g=>g.min>0).flatMap(g=>g.choices).filter(c=>c.name===item.option);
    const optional=groups.filter(g=>g.min===0).flatMap(g=>g.choices).filter(c=>item.extras?.includes(c.name));
    selected=[...new Set([...required,...optional].map(c=>c.id))];
  }
  const validChoices=selected.every(id=>all.some(c=>c.id===id))&&new Set(selected).size===selected.length&&groups.every(g=>{const n=g.choices.filter(c=>selected.includes(c.id)).length;return n>=g.min&&n<=g.max;});
  const issue=p.available===false?'Ce plat est temporairement indisponible.':!validChoices?'Les options ont changé. Personnalisez à nouveau ce plat.':undefined;
  const price=(cents(p.price)+all.filter(c=>selected.includes(c.id)).reduce((sum,c)=>sum+cents(c.price),0))/100;
  return {...item,product:p,choices:selected,choiceNames:all.filter(c=>selected.includes(c.id)).map(c=>c.name),unitPrice:price,issue,option:undefined,extras:undefined};
}
export function useCart(){
  const [items,setItems]=useState<CartItem[]>(readCart);
  const [notice,setNotice]=useState('');
  useEffect(()=>{try{localStorage.setItem('stc-cart-v2',JSON.stringify(items));localStorage.removeItem('smash-cart');}catch{/* Cart still works in memory. */}},[items]);
  const reconcile=useCallback((products:Product[])=>{
    setItems(old=>{
      let changed=false;
      const updated=old.map(item=>{const next=checkedItem(item,products);if(item.unitPrice!==next.unitPrice||next.issue)changed=true;return next;});
      if(changed)setNotice('Votre panier a été actualisé selon la carte du restaurant. Vérifiez les prix et les options.');
      return updated;
    });
  },[]);
  const add=useCallback((item:CartItem)=>setItems(old=>{const found=old.find(i=>i.key===item.key);return found?old.map(i=>i.key===item.key?{...item,quantity:Math.min(20,i.quantity+item.quantity)}:i):[...old,{...item,quantity:Math.min(20,item.quantity)}];}),[]);
  const update=useCallback((key:string,delta:number)=>setItems(old=>old.map(i=>i.key===key?{...i,quantity:Math.min(20,i.quantity+delta)}:i).filter(i=>i.quantity>0)),[]);
  const remove=useCallback((key:string)=>setItems(old=>old.filter(i=>i.key!==key)),[]);
  const clear=useCallback(()=>{setItems([]);setNotice('');},[]);
  return {items,add,update,remove,clear,reconcile,notice,dismissNotice:()=>setNotice(''),count:items.reduce((n,i)=>n+i.quantity,0),total:items.reduce((n,i)=>n+cents(i.unitPrice)*i.quantity,0)/100,hasIssues:items.some(i=>!!i.issue)};
}
export type CartState=ReturnType<typeof useCart>;
