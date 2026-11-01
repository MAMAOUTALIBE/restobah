import {useEffect,useState} from 'react';
import {Flame,Heart,PackageCheck,MapPin,Plus,LogOut,Trash2,Pencil,ArrowRight,LockKeyhole,UserRound,Eye,EyeOff} from 'lucide-react';
import {ApiError,messageOf,restaurantApi,validDetailResponse} from '../services/api';
import type {Address} from '../types';
import {isAmbiguousAuthError,type SessionState} from '../store/useSession';
import type {View} from './Navigation';

import './accounts.css';

export type AccountEntryMode='login'|'register';
export interface PasswordResetFeedback {kind:'success'|'error';message:string}
type AuthMode=AccountEntryMode|'reset'|'confirm';
const blankAddress:Omit<Address,'id'>={label:'Maison',name:'',phone:'',address:'',postal:'',city:''};
export function Account({session,onNavigate,favoriteCount,onDeleted,initialMode='login',initialCustomer,returnToCheckout=false,onAuthenticated,onContinue,resetFeedback,onPasswordReset}:{session:SessionState;onNavigate:(v:View)=>void;favoriteCount:number;onDeleted:(message:string)=>void;initialMode?:AccountEntryMode;initialCustomer?:{name:string;email:string};returnToCheckout?:boolean;onAuthenticated?:(mode:AccountEntryMode)=>void;onContinue?:()=>void;resetFeedback?:PasswordResetFeedback|null;onPasswordReset:(feedback:PasswordResetFeedback)=>void}){
  const resetParams=new URLSearchParams(window.location.search);
  const [mode,setMode]=useState<AuthMode>(resetParams.has('reset_uid')&&resetParams.has('reset_token')?'confirm':initialMode);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const [passwordVisible,setPasswordVisible]=useState(false);
  const [resetAvailability,setResetAvailability]=useState<'loading'|'available'|'unavailable'|'error'>('loading');
  const [resetCheck,setResetCheck]=useState(0);
  const [profile,setProfile]=useState(()=>({name:session.user?.name||'',phone:session.user?.phone||''}));
  const [profileBusy,setProfileBusy]=useState(false);
  const [profileError,setProfileError]=useState('');
  const [profileSuccess,setProfileSuccess]=useState('');
  const [addresses,setAddresses]=useState<Address[]>([]);
  const [addressesLoading,setAddressesLoading]=useState(false);
  const [addressesError,setAddressesError]=useState('');
  const [editing,setEditing]=useState<number|null|undefined>(undefined);
  const [draft,setDraft]=useState<Omit<Address,'id'>>(blankAddress);
  const [addressBusy,setAddressBusy]=useState(false);
  const [deleting,setDeleting]=useState(false);
  const [deleteError,setDeleteError]=useState('');
  const user=session.user;
  async function loadAddresses(){setAddressesLoading(true);setAddressesError('');try{setAddresses(await restaurantApi.getAddresses());}catch(err){setAddressesError(messageOf(err));}finally{setAddressesLoading(false);}}
  useEffect(()=>{let alive=true;setAddresses([]);if(!user)return;setAddressesLoading(true);restaurantApi.getAddresses().then(value=>{if(alive)setAddresses(value);}).catch(err=>{if(alive)setAddressesError(messageOf(err));}).finally(()=>{if(alive)setAddressesLoading(false);});return()=>{alive=false;};},[user?.id]);
  useEffect(()=>{
    if(mode!=='reset')return;
    let alive=true;setResetAvailability('loading');
    restaurantApi.authCapabilities().then(data=>{if(alive)setResetAvailability(data.passwordResetAvailable===true?'available':'unavailable');}).catch(()=>{if(alive)setResetAvailability('error');});
    return()=>{alive=false;};
  },[mode,resetCheck]);
  function switchMode(value:AuthMode){setMode(value);setError('');setSuccess('');setPasswordVisible(false);if(value==='reset')setResetAvailability('loading');}
  async function authenticate(form:HTMLFormElement){
    if(busy||session.loading||(mode==='reset'&&resetAvailability!=='available'))return;
    const data=new FormData(form);
    const email=String(data.get('email')||'').trim();
    const password=String(data.get('password')||'');
    const confirmation=String(data.get('confirmation')||'');
    if(mode==='confirm'&&password!==confirmation){setError('Les deux mots de passe doivent être identiques.');return;}
    const mutation=mode==='reset'?undefined:session.beginIdentityMutation();if(mutation===null)return;
    setBusy(true);setError('');setSuccess('');
    try{
      if(mode==='reset'){const response=await restaurantApi.passwordReset(email);if(!validDetailResponse(response))throw new ApiError('La réponse du compte est invalide.',502);setSuccess(response.detail);}
      else if(mode==='confirm'){
        async function finishReset(feedback:PasswordResetFeedback){
          window.history.replaceState({},'',window.location.pathname);setMode('login');setPasswordVisible(false);form.reset();
          onPasswordReset(feedback);await session.closeAfterPasswordReset();
        }
        try{
          const response=await restaurantApi.passwordConfirm({uid:resetParams.get('reset_uid')||'',token:resetParams.get('reset_token')||'',password});
          if(!validDetailResponse(response))throw new ApiError('La réponse du compte est invalide.',502);
          await finishReset({kind:'success',message:response.detail||'Votre mot de passe a été modifié. Vous pouvez vous connecter.'});
        }catch(err){
          if(err instanceof ApiError&&(err.status===0||err.status>=500)){
            await finishReset({kind:'error',message:'La réponse du serveur n’a pas pu être vérifiée. Essayez de vous connecter avec le nouveau mot de passe. Si nécessaire, rouvrez votre lien de réinitialisation.'});
          }else throw err;
        }
      }else{
        try{
          const response=mode==='login'?await restaurantApi.login({email,password}):await restaurantApi.register({email,password,name:String(data.get('name')||'').trim()});
          if(!response?.user||typeof response.user.email!=='string'||response.user.email.trim().toLowerCase()!==email.toLowerCase())throw new ApiError('La réponse du compte est invalide.',502);
          session.signedIn(response.user);onAuthenticated?.(mode);
        }catch(err){
          if(!isAmbiguousAuthError(err))throw err;
          const verified=await session.refresh({email});
          // A session proves sign-in, but cannot prove that this attempt created an account.
          if(verified)onAuthenticated?.('login');
          else if(verified===null)throw err;
        }
      }
    }catch(err){setError(messageOf(err));}finally{if(mutation!==undefined)session.finishIdentityMutation(mutation);setBusy(false);}
  }
  return <section className="subpage account-page"><span className="small-label">BIENVENUE CHEZ VOUS</span><h1>Mon espace gourmand</h1>
    {session.loading?<div className="panel-loading" role="status">Chargement de votre compte…</div>:session.error?<div className="notice error" role="alert">{session.error}<button className="text-button" onClick={()=>void session.refresh()}>Réessayer</button></div>:null}
    {resetFeedback&&<p className={resetFeedback.kind==='success'?'success-message':'notice error'} role={resetFeedback.kind==='success'?'status':'alert'}>{resetFeedback.message}</p>}
    {session.notice&&<p className="notice" role="status">{session.notice}</p>}
    {user&&mode!=='confirm'?<div inert={session.loading} aria-busy={session.loading}>
      <div className="account-card"><div className="account-heading"><span className="account-avatar"><Flame size={32}/></span><div><h2>Bonjour, {user.name} !</h2><p className="muted">{user.email}</p></div></div>
        <button className="account-link" onClick={()=>onNavigate('Favoris')}><Heart/>Mes favoris <span>{favoriteCount}<ArrowRight size={17}/></span></button>
        <button className="account-link" onClick={()=>onNavigate('Commandes')}><PackageCheck/>Mes commandes <span><ArrowRight size={17}/></span></button>
        <button className="account-link" disabled={busy||session.loading} onClick={async()=>{setBusy(true);setError('');try{await session.logout();setMode('login');setAddresses([]);setEditing(undefined);setSuccess('Vous êtes déconnecté.');}catch(err){setError(messageOf(err));}finally{setBusy(false);}}}><LogOut/>Se déconnecter</button>
      </div>
      <div className="account-card profile-card"><div className="account-section-heading"><h2><UserRound size={20}/> Mes informations</h2></div>
        <p className="muted">Vos coordonnées seront proposées pour vos prochaines commandes.</p>
        <form className="checkout profile-form" onSubmit={async e=>{e.preventDefault();setProfileBusy(true);setProfileError('');setProfileSuccess('');try{const saved=await session.updateProfile({name:profile.name.trim(),phone:profile.phone.trim()});setProfile({name:saved.name,phone:saved.phone||''});setProfileSuccess('Vos informations sont enregistrées.');}catch(err){setProfileError(messageOf(err));}finally{setProfileBusy(false);}}}>
          <label>Nom du compte<input required minLength={2} maxLength={100} autoComplete="name" value={profile.name} onChange={e=>{setProfile({...profile,name:e.target.value});setProfileSuccess('');}}/></label>
          <label>Téléphone du compte (facultatif)<input type="tel" autoComplete="tel" maxLength={24} pattern={String.raw`[+0-9 .\(\)\-]{10,24}`} value={profile.phone} onChange={e=>{setProfile({...profile,phone:e.target.value});setProfileSuccess('');}} placeholder="06 12 34 56 78"/></label>
          <label>E-mail de connexion<input type="email" value={user.email} readOnly autoComplete="email"/></label>
          {profileError&&<p className="error" role="alert">{profileError}</p>}{profileSuccess&&<p className="success-message" role="status">{profileSuccess}</p>}
          <button className="primary" disabled={profileBusy} type="submit">{profileBusy?'Enregistrement…':'Enregistrer mes informations'}</button>
        </form>
      </div>
      <div className="account-card address-card"><div className="account-section-heading"><h2><MapPin size={20}/> Mes adresses</h2><button className="text-button" onClick={()=>{setEditing(null);setDraft({...blankAddress,name:user.name,phone:user.phone||''});setAddressesError('');}}><Plus size={16}/>Ajouter</button></div>
        {addressesLoading?<p className="muted" role="status">Chargement des adresses…</p>:!addresses.length&&editing===undefined?<p className="muted">Enregistrez une adresse pour vos prochaines livraisons.</p>:null}
        {addressesError&&<p className="error" role="alert">{addressesError}<button className="text-button" onClick={()=>void loadAddresses()}>Réessayer</button></p>}
        {addresses.map(address=><article className="saved-address" key={address.id}><div><h3>{address.label}</h3><p>{address.name}<br/>{address.address}<br/>{address.postal} {address.city}<br/>{address.phone}</p></div><div className="address-tools"><button className="icon-button" aria-label={`Modifier l’adresse ${address.label}`} onClick={()=>{const {id,...fields}=address;setDraft(fields);setEditing(id);setAddressesError('');}}><Pencil size={15}/></button><button className="icon-button" disabled={addressBusy} aria-label={`Supprimer l’adresse ${address.label}`} onClick={async()=>{setAddressBusy(true);try{await restaurantApi.deleteAddress(address.id);setAddresses(old=>old.filter(a=>a.id!==address.id));}catch(err){setAddressesError(messageOf(err));}finally{setAddressBusy(false);}}}><Trash2 size={15}/></button></div></article>)}
        {editing!==undefined&&<form className="checkout address-form" onSubmit={async e=>{e.preventDefault();setAddressBusy(true);setAddressesError('');try{const saved=await restaurantApi.saveAddress(draft,editing??undefined);setAddresses(old=>editing===null?[...old,saved]:old.map(a=>a.id===editing?saved:a));setEditing(undefined);}catch(err){setAddressesError(messageOf(err));}finally{setAddressBusy(false);}}}>
          <h3>{editing===null?'Nouvelle adresse':'Modifier l’adresse'}</h3>
          <label>Nom de cette adresse<input required maxLength={60} value={draft.label} onChange={e=>setDraft({...draft,label:e.target.value})} placeholder="Maison, bureau…"/></label>
          <label>Destinataire<input required autoComplete="name" maxLength={100} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
          <label>Téléphone de livraison<input required type="tel" autoComplete="tel" maxLength={25} pattern={String.raw`[+0-9 .\(\)\-]{10,25}`} value={draft.phone} onChange={e=>setDraft({...draft,phone:e.target.value})}/></label>
          <label>Rue et numéro<input required autoComplete="street-address" maxLength={200} value={draft.address} onChange={e=>setDraft({...draft,address:e.target.value})}/></label>
          <div className="form-row"><label>Code postal de l’adresse<input required inputMode="numeric" pattern="[0-9]{5}" value={draft.postal} onChange={e=>setDraft({...draft,postal:e.target.value})}/></label><label>Ville de l’adresse<input required maxLength={100} autoComplete="address-level2" value={draft.city} onChange={e=>setDraft({...draft,city:e.target.value})}/></label></div>
          <div className="form-buttons"><button className="primary" disabled={addressBusy} type="submit">{addressBusy?'Enregistrement…':'Enregistrer l’adresse'}</button><button className="text-button" type="button" onClick={()=>setEditing(undefined)}>Annuler</button></div>
        </form>}
      </div>
      <div className="account-card delete-card"><div className="account-section-heading"><h2><Trash2 size={20}/> Supprimer mon compte</h2>{!deleting&&<button className="text-button" onClick={()=>{setDeleting(true);setDeleteError('');}}>Supprimer</button>}</div>
        {deleting&&<form className="checkout" onSubmit={async e=>{e.preventDefault();if(session.loading)return;const mutation=session.beginIdentityMutation();if(mutation===null)return;const password=String(new FormData(e.currentTarget).get('password')||'');setBusy(true);setDeleteError('');try{const response=await restaurantApi.deleteAccount(password);if(!validDetailResponse(response))throw new ApiError('La réponse du compte est invalide.',502);session.signedOut(user.id);onDeleted(response.detail);}catch(err){if(isAmbiguousAuthError(err))await session.verifyAfterDeletion();else setDeleteError(messageOf(err));}finally{session.finishIdentityMutation(mutation);setBusy(false);}}}>
          <p className="muted">Votre compte, vos adresses et vos favoris seront supprimés. Les commandes déjà passées restent enregistrées par le restaurant.</p>
          <label>Mot de passe actuel<input name="password" type="password" required maxLength={128} autoComplete="current-password"/></label>
          {deleteError&&<p className="error" role="alert">{deleteError}</p>}
          <div className="form-buttons"><button className="primary" disabled={busy} type="submit">{busy?'Suppression…':'Supprimer définitivement mon compte'}</button><button className="text-button" type="button" onClick={()=>setDeleting(false)}>Annuler</button></div>
        </form>}
      </div>
    </div>:<div className="account-card auth-card"><span className="account-avatar"><LockKeyhole size={30}/></span>
      {mode==='login'||mode==='register'?<div className="auth-tabs" role="group" aria-label="Choisir une action"><button disabled={busy} aria-pressed={mode==='login'} className={mode==='login'?'active':''} onClick={()=>switchMode('login')}>Connexion</button><button disabled={busy} aria-pressed={mode==='register'} className={mode==='register'?'active':''} onClick={()=>switchMode('register')}>Créer un compte</button></div>:<h2>{mode==='reset'?'Mot de passe oublié ?':'Choisir un nouveau mot de passe'}</h2>}
      {(mode!=='reset'||resetAvailability==='available')&&<p className="muted">{mode==='login'?'Retrouvez vos adresses, vos favoris et vos commandes.':mode==='register'?'Trois informations pour retrouver vos commandes et gagner du temps.':mode==='reset'?'Indiquez l’adresse e-mail utilisée pour votre compte.':'Le lien de réinitialisation ne peut être utilisé qu’une fois.'}</p>}
      {mode==='reset'&&(resetAvailability==='loading'?<p className="notice" role="status">Vérification de la récupération par e-mail…</p>:resetAvailability==='unavailable'?<p className="notice" role="status">La récupération par e-mail n’est pas encore disponible. Réessayez plus tard.</p>:resetAvailability==='error'?<div className="notice error" role="alert">Impossible de vérifier la récupération par e-mail.<button className="text-button" onClick={()=>setResetCheck(value=>value+1)}>Réessayer</button></div>:null)}
      {returnToCheckout&&<p className="auth-cart-return" role="status">Votre panier vous attend. Vous le retrouverez juste après.</p>}
      <form className="checkout" onSubmit={e=>{e.preventDefault();void authenticate(e.currentTarget);}}>
        {mode==='register'&&<label>Nom complet<input name="name" required disabled={busy} minLength={2} maxLength={100} autoComplete="name" defaultValue={initialCustomer?.name} placeholder="Camille Martin"/></label>}
        {mode!=='confirm'&&(mode!=='reset'||resetAvailability==='available')&&<label>Adresse e-mail<input name="email" type="email" required disabled={busy} maxLength={254} autoComplete="email" defaultValue={initialCustomer?.email} placeholder="camille@exemple.fr"/></label>}
        {mode!=='reset'&&<div className="account-password"><label htmlFor="account-password">{mode==='confirm'?'Nouveau mot de passe':'Mot de passe'}</label><div className="account-password-control"><input id="account-password" name="password" type={passwordVisible?'text':'password'} required disabled={busy} minLength={mode==='login'?1:10} maxLength={128} autoComplete={mode==='login'?'current-password':'new-password'} aria-describedby={mode==='login'?undefined:'account-password-help'}/><button type="button" disabled={busy} aria-label={passwordVisible?'Masquer le mot de passe':'Afficher le mot de passe'} aria-pressed={passwordVisible} aria-controls="account-password" onClick={()=>setPasswordVisible(value=>!value)}>{passwordVisible?<EyeOff size={18}/>:<Eye size={18}/>}<span>{passwordVisible?'Masquer':'Afficher'}</span></button></div></div>}
        {(mode==='register'||mode==='confirm')&&<p id="account-password-help" className="field-help">Au moins 10 caractères. Évitez les mots courants et vos informations personnelles.</p>}
        {mode==='confirm'&&<label>Confirmer le mot de passe<input name="confirmation" type="password" required disabled={busy} minLength={10} maxLength={128} autoComplete="new-password"/></label>}
        {error&&<p className="error" role="alert">{error}</p>}{success&&<p className="success-message" role="status">{success}</p>}
        <button className="primary full" type="submit" disabled={busy||session.loading||(mode==='reset'&&resetAvailability!=='available')}>{busy?'Veuillez patienter…':mode==='login'?'Se connecter':mode==='register'?'Créer mon compte':mode==='reset'?'Envoyer le lien de réinitialisation':'Enregistrer le nouveau mot de passe'}</button>
      </form>
      {mode==='login'?<button className="text-button" disabled={busy} onClick={()=>switchMode('reset')}>Mot de passe oublié</button>:<button className="text-button" disabled={busy} onClick={()=>{switchMode('login');if(mode==='confirm')window.history.replaceState({},'',window.location.pathname);}}>Revenir à la connexion</button>}
      <button className="account-guest" disabled={busy||session.loading||session.recoveryRequired||!!session.error} onClick={()=>{if(!session.loading&&!session.recoveryRequired&&!session.error){if(onContinue)onContinue();else onNavigate('Carte');}}}>{returnToCheckout?'Continuer ma commande sans compte':'Continuer sans compte'} <ArrowRight size={15}/></button>
    </div>}
    {user&&error&&<p className="error" role="alert">{error}</p>}{user&&success&&<p className="success-message" role="status">{success}</p>}
  </section>;
}
