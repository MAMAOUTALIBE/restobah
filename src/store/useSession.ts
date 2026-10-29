import {useCallback,useEffect,useRef,useState} from 'react';
import type {User} from '../types';
import {messageOf,restaurantApi} from '../services/api';
import {readStorage} from './useCart';

export const validIds=(v:unknown):v is number[]=>Array.isArray(v)&&v.every(id=>Number.isInteger(id)&&id>0);
const guestIds=()=>readStorage('stc-favorites-guest',readStorage('smash-favorites',[],validIds),validIds);
function writeIds(key:string,value:number[]){try{localStorage.setItem(key,JSON.stringify(value));}catch{/* memory fallback */}}
export function useSession(){
  const [user,setUser]=useState<User|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const refresh=useCallback(async()=>{setLoading(true);setError('');try{const data=await restaurantApi.me();setUser(data.user);}catch(err){setError(messageOf(err));}finally{setLoading(false);}},[]);
  useEffect(()=>{void refresh();},[refresh]);
  const signedIn=useCallback((value:User)=>{setUser(value);setError('');},[]);
  const logout=useCallback(async()=>{await restaurantApi.logout();setUser(null);},[]);
  // After a server-side account deletion: the session is already closed, only local traces remain.
  const signedOut=useCallback((id:number)=>{setUser(null);try{localStorage.removeItem(`stc-favorites-${id}`);}catch{/* optional storage */}},[]);
  return {user,loading,error,refresh,signedIn,logout,signedOut};
}
export type SessionState=ReturnType<typeof useSession>;
export function useFavorites(user:User|null){
  const [ids,setIds]=useState<number[]>(guestIds);
  const [ready,setReady]=useState(!user);
  const [error,setError]=useState('');
  const queue=useRef<Promise<unknown>>(Promise.resolve());
  const actor=useRef<number|null>(null);
  const [revision,setRevision]=useState(0);
  const retry=()=>setRevision(v=>v+1);
  useEffect(()=>{
    let alive=true;
    const userId=user?.id??null;actor.current=userId;
    setError('');setReady(false);
    if(!userId){setIds(guestIds());setReady(true);return;}
    setIds(readStorage(`stc-favorites-${userId}`,[],validIds));
    void (async()=>{
      try{
        const remote=await restaurantApi.getFavorites();
        if(!alive||actor.current!==userId)return;
        const guest=guestIds();
        const merged=[...new Set([...remote,...guest])];
        const result=guest.length?await restaurantApi.saveFavorites(merged):remote;
        if(!alive||actor.current!==userId)return;
        setIds(result);writeIds(`stc-favorites-${userId}`,result);writeIds('stc-favorites-guest',[]);try{localStorage.removeItem('smash-favorites');}catch{/* optional storage */}
        setReady(true);
      }catch(err){if(alive){setError(messageOf(err));setReady(false);}}
    })();
    return()=>{alive=false;};
  },[user?.id,revision]);
  const toggle=useCallback((id:number)=>{
    if(!ready){setError('Les favoris sont en cours de synchronisation. Réessayez.');return;}
    const owner=user?.id??null;
    setIds(old=>{
      const next=old.includes(id)?old.filter(value=>value!==id):[...old,id];
      const key=owner?`stc-favorites-${owner}`:'stc-favorites-guest';
      writeIds(key,next);
      if(owner){queue.current=queue.current.catch(()=>undefined).then(async()=>{if(actor.current!==owner)return;try{await restaurantApi.saveFavorites(next);if(actor.current===owner)setError('');}catch(err){if(actor.current===owner){setError(`Synchronisation des favoris impossible : ${messageOf(err)}`);}}});}
      return next;
    });
  },[ready,user?.id]);
  return {ids,toggle,ready,error,retry};
}
