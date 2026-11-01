import {useCallback,useEffect,useRef,useState} from 'react';
import type {User} from '../types';
import {ApiError,messageOf,restaurantApi,validDetailResponse} from '../services/api';
import {readStorage} from './useCart';

export const validIds=(v:unknown):v is number[]=>Array.isArray(v)&&v.every(id=>Number.isInteger(id)&&id>0);
const guestIds=()=>readStorage('stc-favorites-guest',readStorage('smash-favorites',[],validIds),validIds);
function writeIds(key:string,value:number[]){try{localStorage.setItem(key,JSON.stringify(value));}catch{/* memory fallback */}}
export const isAmbiguousAuthError=(error:unknown)=>error instanceof ApiError&&(error.status===0||error.status>=500);
type IdentityExpectation={email?:string;anonymous?:boolean};
function validSessionUser(value:unknown):value is User{
  if(!value||typeof value!=='object')return false;
  const user=value as Partial<User>;
  return typeof user.id==='number'&&Number.isSafeInteger(user.id)&&user.id>0&&typeof user.name==='string'&&typeof user.email==='string'&&!!user.email.trim()&&(user.phone===undefined||typeof user.phone==='string');
}
export function useSession(){
  const [user,setUser]=useState<User|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [recoveryRequired,setRecoveryRequired]=useState(false);
  const generation=useRef(0);
  const activeMutation=useRef<number|null>(null);
  const beginIdentityMutation=useCallback(()=>{
    if(activeMutation.current!==null)return null;
    const current=++generation.current;activeMutation.current=current;setLoading(true);return current;
  },[]);
  const finishIdentityMutation=useCallback((current:number)=>{
    if(activeMutation.current!==current)return;
    activeMutation.current=null;if(current===generation.current)setLoading(false);
  },[]);
  const pendingLogout=useRef(false);
  const pendingExpectation=useRef<IdentityExpectation|null>(null);
  const refresh=useCallback(async(expectation?:IdentityExpectation):Promise<User|null|undefined>=>{
    if(expectation){pendingExpectation.current=expectation;pendingLogout.current=false;setUser(null);setRecoveryRequired(true);}
    const current=++generation.current;setLoading(true);setError('');
    try{
      // A retry may close an uncertain session, but never repeats an account deletion.
      if(pendingLogout.current){const closed=await restaurantApi.logout();if(!validDetailResponse(closed))throw new ApiError('La réponse du compte est invalide.',502);if(current!==generation.current)return;pendingLogout.current=false;pendingExpectation.current={anonymous:true};}
      const data=await restaurantApi.me();if(current!==generation.current)return;
      if(!data||(data.user!==null&&!validSessionUser(data.user)))throw new ApiError('La réponse du compte est invalide.',502);
      const expected=pendingExpectation.current;
      if(data.user&&(expected?.anonymous||(expected?.email&&data.user.email.trim().toLowerCase()!==expected.email.trim().toLowerCase()))){
        pendingLogout.current=true;pendingExpectation.current=null;setUser(null);setRecoveryRequired(true);
        setError(expected?.email?'Le compte ouvert ne correspond pas à l’adresse saisie. Connectez-vous ou réessayez la vérification.':'Votre ancienne session n’a pas été fermée. Réessayez ou connectez-vous.');
        return;
      }
      pendingLogout.current=false;pendingExpectation.current=null;setRecoveryRequired(false);setUser(data.user);return data.user;
    }catch(err){
      if(current===generation.current){
        if(pendingExpectation.current?.anonymous)pendingLogout.current=true;
        setUser(null);setRecoveryRequired(true);
        setError(pendingExpectation.current?'Nous n’avons pas pu vérifier votre compte. Réessayez ou connectez-vous.':messageOf(err));
      }
    }finally{if(current===generation.current)setLoading(false);}
  },[]);
  useEffect(()=>{void refresh();},[refresh]);
  const acceptIdentity=useCallback((value:User|null)=>{generation.current++;pendingLogout.current=false;pendingExpectation.current=null;setRecoveryRequired(false);setUser(value);setLoading(false);setError('');setNotice('');},[]);
  const signedIn=useCallback((value:User)=>{if(!validSessionUser(value))throw new ApiError('La réponse du compte est invalide.',502);acceptIdentity(value);},[acceptIdentity]);
  const closeAfterPasswordReset=useCallback(async()=>{
    const current=++generation.current;pendingLogout.current=true;pendingExpectation.current=null;setRecoveryRequired(true);setNotice('');
    // A changed password invalidates Django's session hash; never keep its old DTO on screen.
    setUser(null);setLoading(true);setError('');
    try{const closed=await restaurantApi.logout();if(!validDetailResponse(closed))throw new ApiError('La réponse du compte est invalide.',502);if(current===generation.current){pendingLogout.current=false;setRecoveryRequired(false);}}
    catch{if(current===generation.current)setError('La fermeture de votre session n’a pas pu être vérifiée. Réessayez.');}
    finally{if(current===generation.current)setLoading(false);}
  },[]);
  const updateProfile=useCallback(async(data:{name:string;phone:string})=>{
    const response=await restaurantApi.updateProfile(data);
    // A profile response must never reopen a session closed in another view.
    setUser(current=>current?.id===response.user.id?response.user:current);
    return response.user;
  },[]);
  const logout=useCallback(async()=>{
    const mutation=beginIdentityMutation();if(mutation===null)throw new Error('Une vérification du compte est déjà en cours.');
    try{const response=await restaurantApi.logout();if(!validDetailResponse(response))throw new ApiError('La réponse du compte est invalide.',502);acceptIdentity(null);}
    catch(err){
      if(!isAmbiguousAuthError(err))throw err;
      const verified=await refresh({anonymous:true});
      if(verified!==null)throw new Error('La déconnexion n’a pas pu être confirmée. Réessayez.');
    }finally{finishIdentityMutation(mutation);}
  },[acceptIdentity,beginIdentityMutation,finishIdentityMutation,refresh]);
  const verifyAfterDeletion=useCallback(async()=>{
    setNotice('La suppression de votre compte n’a pas pu être confirmée. Vérifiez votre compte en vous reconnectant.');
    await refresh({anonymous:true});
  },[refresh]);
  // Only a confirmed deletion removes the account's cached favourites.
  const signedOut=useCallback((id:number)=>{acceptIdentity(null);try{localStorage.removeItem(`stc-favorites-${id}`);}catch{/* optional storage */}},[acceptIdentity]);
  return {user,loading,error,notice,recoveryRequired,refresh,signedIn,updateProfile,logout,signedOut,closeAfterPasswordReset,verifyAfterDeletion,beginIdentityMutation,finishIdentityMutation};
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
