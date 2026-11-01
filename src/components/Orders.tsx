import {useCallback,useEffect,useRef,useState} from 'react';
import {Check,ChefHat,PackageCheck,RefreshCw,CreditCard,ArrowRight} from 'lucide-react';
import {restaurantApi,ApiError,messageOf} from '../services/api';
import {forgetCheckoutForOrder,redirectToPayment} from '../services/payment';
import {euro,statusLabels,type GuestOrderRef,type Order,type User} from '../types';

function paymentLabel(order:Order){
  if(order.paymentMethod==='on_site'||order.paymentStatus==='due'){
    if(order.paymentStatus==='paid')return 'Réglé sur place';
    if(order.paymentStatus==='refunded')return 'Remboursé sur place';
    if(order.paymentStatus==='cancelled')return 'Règlement annulé';
    return order.mode==='Livraison'?'À régler à la livraison':'À régler au restaurant';
  }
  return order.paymentStatus==='simulated'?'Paiement simulé · Aucun prélèvement':order.paymentStatus==='paid'?'Paiement confirmé':order.paymentStatus==='refunded'?'Paiement remboursé':order.paymentStatus==='failed'?'Le paiement a échoué':order.paymentStatus==='cancelled'?'Paiement annulé':'Paiement en attente';
}

export function Orders({user,references,paymentReturn,onBrowse,onPaid}:{user:User|null;references:GuestOrderRef[];paymentReturn:string|null;onBrowse:()=>void;onPaid:(order:Order)=>void}){
  const [orders,setOrders]=useState<Order[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState<string|null>(null);
  const [actionError,setActionError]=useState('');
  const currentOrders=useRef<Order[]>([]);
  const pollIndex=useRef(0);
  const active=useRef(true);
  useEffect(()=>{currentOrders.current=orders;},[orders]);
  const refresh=useCallback(async(silent=false)=>{
    if(!silent)setLoading(true);
    try{
      // Guest orders of this device stay visible after signing in; account orders take precedence.
      const linked=(o:Order)=>references.some(ref=>ref.id===o.id);
      const ongoing=currentOrders.current.filter(o=>linked(o)&&!['completed','cancelled'].includes(o.status));
      const poll=ongoing.length?ongoing[pollIndex.current++%ongoing.length]:null;
      const targets=silent?(poll?references.filter(ref=>ref.id===poll.id):[]):references;
      if(silent&&!user&&!targets.length)return;
      const [account,results]=await Promise.all([user?restaurantApi.getOrders():Promise.resolve([] as Order[]),Promise.allSettled(targets.map(ref=>restaurantApi.getOrder(ref.id,ref.accessToken)))]);
      if(!active.current)return;
      const found=results.flatMap((result,index)=>result.status==='fulfilled'?[{...result.value,accessToken:targets[index].accessToken}]:[]);
      const missing=results.some(result=>result.status==='rejected');
      setOrders(old=>{
        const previous=old.filter(linked);
        const guest=silent||(missing&&!found.length)?previous.map(order=>found.find(next=>next.id===order.id)||order):found;
        return [...account,...guest.filter(order=>!account.some(a=>a.id===order.id))].sort((a,b)=>b.date.localeCompare(a.date));
      });
      setError(missing?'Certaines commandes ne sont pas accessibles. Vérifiez votre connexion puis actualisez.':'');
      const updated=[...account,...found];
      updated.filter(o=>o.status==='cancelled'||o.paymentStatus==='refunded').forEach(o=>forgetCheckoutForOrder(o.id));
      updated.filter(o=>o.paymentStatus==='paid').forEach(onPaid);
    }catch(err){if(active.current)setError(messageOf(err));}finally{if(active.current)setLoading(false);}
  },[user?.id,references,onPaid]);
  useEffect(()=>{active.current=true;setOrders([]);void refresh();const timer=window.setInterval(()=>{if(document.visibilityState==='visible')void refresh(true);},30000);return()=>{active.current=false;window.clearInterval(timer);};},[refresh]);
  async function pay(order:Order){
    setBusy(order.id);setActionError('');
    try{const result=await restaurantApi.createPayment(order.id,order.accessToken||references.find(r=>r.id===order.id)?.accessToken);redirectToPayment(result.url);}catch(err){setActionError(messageOf(err));if(err instanceof ApiError&&err.status===409)void refresh(true);}finally{setBusy(null);}
  }
  const returned=paymentReturn;
  return <section className="subpage orders-page"><span className="small-label">ON S’OCCUPE DE TOUT</span><div className="page-title-row"><h1>Mes commandes</h1><button className="text-button" disabled={loading} onClick={()=>void refresh()}><RefreshCw size={15}/>Actualiser</button></div><p className="muted">{user?'Vos commandes et leur suivi, mis à jour par le restaurant.':'Retrouvez les commandes invitées passées sur cet appareil.'}</p>
    {returned&&<p className="notice" role="status">{(returned==='cancel'||returned==='cancelled')?'Le paiement a été interrompu. Votre panier est conservé. Vous pouvez reprendre le paiement ci-dessous.':'Le résultat du paiement est en cours de vérification auprès du serveur. Le statut ci-dessous fait foi.'}</p>}
    {loading&&<p className="panel-loading" role="status">Chargement de vos commandes…</p>}
    {error&&<div className="notice error" role="alert">{error}<button className="text-button" onClick={()=>void refresh()}>Réessayer</button></div>}
    {actionError&&<p className="error" role="alert">{actionError}</p>}
    {!loading&&!orders.length&&!error&&<div className="empty"><PackageCheck size={45}/><h3>Votre première commande vous attend.</h3><button className="primary" onClick={onBrowse}>Découvrir la carte <ArrowRight size={17}/></button></div>}
    {orders.map(order=>{
      const milestones=['confirmed','preparing','ready'] as const;
      const current=order.status==='completed'?3:milestones.indexOf(order.status as typeof milestones[number]);
      return <article className="order-card" key={order.id}>
        <div className="order-heading"><div><h3>Commande {order.id}</h3><p>{new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(order.date))} · {order.mode}</p></div><strong>{euro(order.total)}</strong></div>
        <div className={`order-status status-${order.status}`}><span/>{statusLabels[order.status]||order.status}</div>
        {order.status!=='cancelled'&&order.status!=='pending_payment'&&<div className="tracking" aria-label={`Suivi : ${statusLabels[order.status]}`}>{milestones.map((status,index)=><div className={index<=current?'done':'pending'} key={status}><span>{index===0?<Check/>:index===1?<ChefHat/>:<PackageCheck/>}</span><p>{statusLabels[status]}</p></div>)}</div>}
        <div className="order-lines">{order.lines.map((line,index)=><div className="order-line" key={index}><div><strong>{line.quantity} × {line.name}</strong>{line.choices.length>0&&<p>{line.choices.join(' · ')}</p>}</div><span>{euro(line.total)}</span></div>)}</div>
        {order.deliveryFee>0&&<p className="order-delivery">Livraison <span>{euro(order.deliveryFee)}</span></p>}
        <p className="payment-note">{paymentLabel(order)}</p>
        {order.paymentMethod!=='on_site'&&(order.paymentStatus==='pending'||order.paymentStatus==='failed')&&order.status!=='cancelled'&&<button className="primary" disabled={busy===order.id} onClick={()=>void pay(order)}><CreditCard size={16}/>{busy===order.id?'Connexion au paiement…':'Reprendre le paiement test'}</button>}
        {order.history.length>0&&<details className="order-events"><summary>Historique du suivi</summary><ol>{order.history.map((event,index)=><li key={index}><span>{statusLabels[event.status]||event.status}</span><time dateTime={event.date}>{new Intl.DateTimeFormat('fr-FR',{dateStyle:'short',timeStyle:'short'}).format(new Date(event.date))}</time></li>)}</ol></details>}
        {order.demoMode&&<span className="demo-pill">Démonstration · Commande enregistrée, aucun repas préparé</span>}
      </article>;
    })}
  </section>;
}
