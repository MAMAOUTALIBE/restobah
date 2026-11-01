import {useEffect,useRef,useState} from 'react';
import {ShoppingBag,Minus,Plus,Trash2,ArrowRight,Store,Truck,ShieldCheck,CreditCard} from 'lucide-react';
import {FoodImage} from './FoodImage';
import {Modal} from './Modal';
import {euro,money,type Address,type Customer,type Order,type OrderPayload,type RestaurantSettings,type User} from '../types';
import {checkedItem,type CartState} from '../store/useCart';
import {ApiError,messageOf,restaurantApi} from '../services/api';
import {forgetCheckoutForOrder,redirectToPayment} from '../services/payment';

const emptyCustomer:Customer={name:'',email:'',phone:'',address:'',postal:'',city:'',note:''};
export const basketSignature=(cart:Pick<CartState,'items'>)=>JSON.stringify(cart.items.map(i=>({id:i.product.id,quantity:i.quantity,choices:[...i.choices].sort()})).sort((a,b)=>`${a.id}${a.choices}`.localeCompare(`${b.id}${b.choices}`)));
export function rememberPaymentBasket(orderId:string,cart:Pick<CartState,'items'>){try{sessionStorage.setItem('stc-payment-cart',JSON.stringify({id:orderId,signature:basketSignature(cart)}));}catch{/* payment still works without recovery */}}
async function requestKey(payload:OrderPayload){
  const buffer=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));
  const fingerprint=Array.from(new Uint8Array(buffer)).map(n=>n.toString(16).padStart(2,'0')).join('');
  try{const saved=JSON.parse(sessionStorage.getItem('stc-checkout-key')||'null') as {fingerprint?:string;key?:string}|null;if(saved?.fingerprint===fingerprint&&typeof saved.key==='string')return saved.key;}catch{/* create a new key */}
  const key=crypto.randomUUID();try{sessionStorage.setItem('stc-checkout-key',JSON.stringify({fingerprint,key}));}catch{/* key retained in mounted form */}return key;
}
export function Cart({cart,settings,refreshSettings,user,onClose,onRegistered,onComplete}:{cart:CartState;settings:RestaurantSettings|null;refreshSettings:()=>Promise<RestaurantSettings>;user:User|null;onClose:()=>void;onRegistered:(o:Order)=>void;onComplete:(o:Order)=>void}){
  const [mode,setMode]=useState<'À emporter'|'Livraison'>(settings?.pickupEnabled===false&&settings.deliveryEnabled!==false?'Livraison':'À emporter');
  const [checkout,setCheckout]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [customer,setCustomer]=useState<Customer>({...emptyCustomer,name:user?.name||'',email:user?.email||''});
  const [addresses,setAddresses]=useState<Address[]>([]);
  const [addressesError,setAddressesError]=useState('');
  const [pendingOrder,setPendingOrder]=useState<Order|null>(null);
  const submission=useRef(false);
  const keyCache=useRef<{payload:string;key:string}|null>(null);
  const actualSettings=settings;
  const delivery=mode==='Livraison'?(actualSettings?.deliveryFee??0):0;
  const total=money(cart.total+delivery);
  const enabled=!!actualSettings&&actualSettings.orderingEnabled&&actualSettings.isOpen;
  const paymentMode=pendingOrder?'stripe':actualSettings?.paymentMode;
  const paymentPlace=mode==='Livraison'?'à la livraison':'au restaurant';
  useEffect(()=>{let alive=true;if(!user)return;restaurantApi.getAddresses().then(data=>{if(alive)setAddresses(data);}).catch(err=>{if(alive)setAddressesError(messageOf(err));});return()=>{alive=false;};},[user?.id]);
  function field(name:keyof Customer,value:string){setCustomer(old=>({...old,[name]:value}));setError('');}
  async function pay(order:Order){
    rememberPaymentBasket(order.id,cart);
    try{const response=await restaurantApi.createPayment(order.id,order.accessToken);redirectToPayment(response.url);}
    catch(error){
      if(error instanceof ApiError&&(error.status===400||error.status===409)){
        let verified:Order|null=null;
        try{verified=await restaurantApi.getOrder(order.id,order.accessToken);}catch{/* An unverified failure must never start another order. */}
        if(verified?.status==='cancelled'){
          forgetCheckoutForOrder(order.id);keyCache.current=null;setPendingOrder(null);
          throw new Error('Cette tentative de paiement est annulée ou expirée. Votre panier est conservé. Vous pouvez valider une nouvelle commande.');
        }
        if(verified?.paymentStatus==='paid'){
          forgetCheckoutForOrder(order.id);cart.clear();onComplete(verified);return;
        }
      }
      throw error;
    }
  }
  async function submit(){
    if(submission.current)return;
    if((mode==='Livraison'&&actualSettings?.deliveryEnabled===false)||(mode==='À emporter'&&actualSettings?.pickupEnabled===false)){setError('Ce mode de commande est temporairement indisponible. Choisissez un autre mode.');return;}
    if(!enabled){setError('Les commandes sont actuellement fermées. Réessayez pendant les horaires d’ouverture.');return;}
    if(!customer.name.trim()||!customer.phone.trim()||!customer.email.trim()){setError('Veuillez renseigner vos coordonnées.');return;}
    if(mode==='Livraison'&&actualSettings?.deliveryPostalCodes.length&&!actualSettings.deliveryPostalCodes.includes(customer.postal||'')){setError('Cette adresse est hors de notre zone de livraison. Choisissez le retrait au restaurant.');return;}
    if(mode==='Livraison'&&cart.total<(actualSettings?.minDeliveryTotal||0)){setError(`Le minimum de commande en livraison est de ${euro(actualSettings?.minDeliveryTotal||0)}.`);return;}
    submission.current=true;setBusy(true);setError('');
    try{
      if(pendingOrder){await pay(pendingOrder);return;}
      const [freshProducts,freshSettings]=await Promise.all([restaurantApi.getProducts(),refreshSettings()]);
      const checked=cart.items.map(item=>checkedItem(item,freshProducts));
      if(checked.some((item,index)=>item.issue||item.unitPrice!==cart.items[index].unitPrice)||freshSettings.deliveryFee!==actualSettings?.deliveryFee){cart.reconcile(freshProducts);setError('La carte ou les tarifs ont changé. Vérifiez votre panier avant de confirmer à nouveau.');return;}
      if(!freshSettings.orderingEnabled||!freshSettings.isOpen){setError('Le restaurant ne prend pas de commandes pour le moment. Votre panier est conservé.');return;}
      if(freshSettings.paymentMode!==actualSettings?.paymentMode||freshSettings.demoMode!==actualSettings?.demoMode){setError('Le mode de paiement a changé. Vérifiez les informations de règlement avant de confirmer à nouveau.');return;}
      const payload:OrderPayload={mode,items:checked.map(i=>({productId:i.product.id,quantity:i.quantity,choices:i.choices})),customer:{name:customer.name.trim(),email:customer.email.trim(),phone:customer.phone.trim(),note:customer.note?.trim(),...(mode==='Livraison'?{address:customer.address?.trim(),postal:customer.postal?.trim(),city:customer.city?.trim()}:{})},paymentMethod:freshSettings.paymentMode};
      const serialized=JSON.stringify(payload);
      const key=keyCache.current?.payload===serialized?keyCache.current.key:await requestKey(payload);
      keyCache.current={payload:serialized,key};
      const order=await restaurantApi.placeOrder(payload,key);
      onRegistered(order);
      if(freshSettings.paymentMode==='stripe'){
        setPendingOrder(order);await pay(order);
      }else{
        cart.clear();try{sessionStorage.removeItem('stc-checkout-key');}catch{/* optional storage */}onComplete(order);
      }
    }catch(err){setError(messageOf(err));}finally{submission.current=false;setBusy(false);}
  }
  return <Modal title="Mon panier" onClose={onClose}><div className="cart-content"><span className="small-label">LE BONHEUR EST PRESQUE LÀ</span><h2>Mon panier <span className="muted">({cart.count})</span></h2>
    {!cart.items.length?<div className="empty"><ShoppingBag size={48}/><h3>Une petite faim ?</h3><p>Votre prochain coup de cœur vous attend dans la carte.</p><button className="primary" onClick={onClose}>Découvrir la carte <ArrowRight size={17}/></button></div>:<>
      {cart.notice&&<div className="notice" role="status">{cart.notice}<button className="text-button" onClick={cart.dismissNotice}>Compris</button></div>}
      <div className="mode-switch">{[{name:'À emporter',icon:Store},{name:'Livraison',icon:Truck}].map(({name,icon:Icon})=><button disabled={busy||!!pendingOrder||(name==='Livraison'&&actualSettings?.deliveryEnabled===false)||(name==='À emporter'&&actualSettings?.pickupEnabled===false)} className={mode===name?'active':''} key={name} onClick={()=>{setMode(name as typeof mode);setError('');}}><Icon size={17}/>{name}</button>)}</div>
      <p className="muted delivery-note">{mode==='À emporter'?`Prêt dans ${actualSettings?.pickupDelay||'quelques minutes'} · ${actualSettings?.address||'Au restaurant'}`:`Livraison · ${actualSettings?.deliveryDelay||'selon la zone'}${actualSettings?.deliveryPostalCodes.length?` · ${actualSettings.deliveryPostalCodes.join(', ')}`:''}`}</p>
      {!enabled&&<p className="notice" role="status">{actualSettings?'Le restaurant ne prend pas de commandes pour le moment.':'Connexion au restaurant en cours. Le panier reste disponible.'}</p>}
      <div className="cart-items">{cart.items.map(i=><div className={`cart-item ${i.issue?'cart-item-invalid':''}`} key={i.key}><FoodImage image={i.product.image}/><div><h3>{i.product.name}</h3><p>{i.choiceNames.join(' · ')||'Recette originale'}</p>{i.issue&&<p className="error">{i.issue}</p>}<strong>{euro(i.unitPrice*i.quantity)}</strong><div className="quantity"><button disabled={busy||!!pendingOrder} aria-label={`Réduire ${i.product.name}`} onClick={()=>cart.update(i.key,-1)}><Minus size={14}/></button><span>{i.quantity}</span><button disabled={busy||!!pendingOrder||i.quantity>=20} aria-label={`Augmenter ${i.product.name}`} onClick={()=>cart.update(i.key,1)}><Plus size={14}/></button></div></div><button className="remove" disabled={busy||!!pendingOrder} aria-label={`Supprimer ${i.product.name}`} onClick={()=>cart.remove(i.key)}><Trash2 size={17}/></button></div>)}</div>
      <div className="totals"><p><span>Sous-total</span><span>{euro(cart.total)}</span></p><p><span>{mode==='Livraison'?'Livraison':'Retrait au restaurant'}</span><span>{delivery?euro(delivery):'Offert'}</span></p><p className="total"><strong>Total TTC</strong><strong>{euro(total)}</strong></p></div>
      {!checkout?<button className="primary full" disabled={!enabled||cart.hasIssues} onClick={()=>setCheckout(true)}>Passer commande <ArrowRight size={18}/></button>:<form className="checkout" onSubmit={e=>{e.preventDefault();void submit();}}><h3>Vos coordonnées</h3>
        {!user&&<p className="muted">Commande invitée · Aucun compte nécessaire.</p>}
        {pendingOrder&&<p className="notice" role="status">La commande {pendingOrder.id} est enregistrée, en attente de paiement. Vous pouvez reprendre son paiement ici ou dans « Commandes ».</p>}
        <fieldset className="checkout-fields" disabled={busy||!!pendingOrder}>
          {mode==='Livraison'&&addresses.length>0&&<label>Utiliser une adresse enregistrée<select defaultValue="" onChange={e=>{const found=addresses.find(a=>a.id===Number(e.target.value));if(found)setCustomer(old=>({...old,name:found.name,phone:found.phone,address:found.address,postal:found.postal,city:found.city}));}}><option value="">Saisir une adresse</option>{addresses.map(a=><option value={a.id} key={a.id}>{a.label} — {a.postal} {a.city}</option>)}</select></label>}
          {addressesError&&<p className="muted">Les adresses enregistrées ne sont pas accessibles. Vous pouvez saisir votre adresse ci-dessous.</p>}
          <label>Nom complet<input name="name" autoComplete="name" minLength={2} maxLength={100} required placeholder="Camille Martin" value={customer.name} onChange={e=>field('name',e.target.value)}/></label>
          <label>Adresse e-mail<input type="email" name="email" autoComplete="email" maxLength={254} required placeholder="camille@exemple.fr" value={customer.email} onChange={e=>field('email',e.target.value)}/></label>
          <label>Téléphone<input type="tel" name="phone" autoComplete="tel" pattern={String.raw`[+0-9 .\(\)\-]{10,18}`} required placeholder="06 12 34 56 78" value={customer.phone} onChange={e=>field('phone',e.target.value)}/></label>
          {mode==='Livraison'&&<><label>Adresse de livraison<input required name="address" maxLength={200} autoComplete="street-address" placeholder="Numéro et rue" value={customer.address} onChange={e=>field('address',e.target.value)}/></label><div className="form-row"><label>Code postal<input name="postal" required pattern="[0-9]{5}" inputMode="numeric" autoComplete="postal-code" placeholder="75011" value={customer.postal} onChange={e=>field('postal',e.target.value)}/></label><label>Ville<input name="city" autoComplete="address-level2" required maxLength={100} placeholder="Paris" value={customer.city} onChange={e=>field('city',e.target.value)}/></label></div></>}
          <label>Une précision ?<textarea name="note" maxLength={1000} placeholder="Instructions pour votre commande (facultatif)" value={customer.note} onChange={e=>field('note',e.target.value)}/></label>
        </fieldset>
        {error&&<p className="error" role="alert">{error}</p>}
        <button disabled={busy||!enabled||cart.hasIssues} className="primary full" type="submit">{paymentMode==='stripe'&&<CreditCard size={16}/>} {busy?'Validation en cours…':pendingOrder?'Réessayer le paiement test':paymentMode==='stripe'?'Continuer vers le paiement test':paymentMode==='on_site'?`Commander et régler ${paymentPlace}`:'Valider la commande de démonstration'}</button>
      </form>}
      <p className="simulation"><ShieldCheck size={16}/>{paymentMode==='on_site'?`Le total de ${euro(total)} sera à régler ${paymentPlace}. Aucun paiement en ligne.`:paymentMode==='stripe'?'Stripe en mode test · Aucun paiement réel.':'Paiement simulé · Aucun prélèvement ne sera effectué.'}</p>
      {actualSettings?.demoMode&&<p className="field-help centered">La commande sera enregistrée pour démonstration. Aucun repas ne sera préparé.</p>}
    </>}
  </div></Modal>;
}
