import {useCallback,useState} from 'react';
import {ArrowRight,ArrowUp,MapPin,Clock,Flame,ShoppingBag,Truck,Heart} from 'lucide-react';
import type {View} from './Navigation';
import type {RestaurantSettings} from '../types';
import {Modal} from './Modal';
import {restaurant} from '../data/restaurant';
import './Footer.css';

type Info='questions'|'allergenes'|'confidentialite';
const shared={
  order:{question:'Comment passer commande ?',answer:'Choisissez un plat, personnalisez-le, puis ajoutez-le au panier. Vous pouvez choisir le retrait au restaurant ou la livraison avant de valider vos coordonnées.'},
  veggie:{question:'Des options végétariennes ?',answer:'Ouvrez les filtres de la carte et cochez « Végétarien » pour retrouver les recettes concernées.'},
  device:{question:'Vos données sur cet appareil',answer:'Le panier, les favoris invités et les références sécurisées des commandes invitées restent dans ce navigateur. Les commandes et les données de votre compte sont conservées sur le serveur. Les favoris de votre compte sont synchronisés après connexion.'},
  contact:{question:'Les coordonnées de commande',answer:'Les coordonnées saisies sont transmises au serveur pour gérer votre commande. Elles ne sont pas conservées dans l’historique local de cet appareil. Les références invitées contiennent une clé d’accès : ne partagez pas le stockage de votre navigateur.'},
};
// Demonstration wording only while STC_DEMO_MODE is on; the restaurant's legal notices are supplied separately.
function information(demo:boolean,settings:RestaurantSettings|null):Record<Info,{title:string;content:{question:string;answer:string}[]}>{
  const delays=`Comptez environ ${settings?.pickupDelay||'15–20 min'} pour le retrait et ${settings?.deliveryDelay||'30–40 min'} pour la livraison`;
  return demo?{
  questions:{title:'Une question ? On vous répond.',content:[shared.order,
    {question:'Quels sont les délais ?',answer:`${delays}. Ces délais sont illustratifs dans cette démonstration.`},
    {question:'Est-ce une vraie commande ?',answer:'Les commandes sont enregistrées sur le serveur et leur suivi est mis à jour par l’équipe dans l’administration. En mode démonstration, aucun repas n’est préparé et aucun paiement réel n’est prélevé.'},
  ]},
  allergenes:{title:'Allergènes & préférences',content:[
    {question:'Avant de choisir votre plat',answer:'Les compositions et les photos sont illustratives. Les plats peuvent notamment contenir du gluten, du lait, des œufs, du soja, du sésame ou de la moutarde. Cette liste n’est pas exhaustive.'},
    {question:'Vous avez une allergie ?',answer:'Une confirmation auprès du restaurant sera nécessaire avant toute commande réelle. La démonstration ne permet pas de garantir l’absence d’un allergène ou de traces.'},
    shared.veggie,
  ]},
  confidentialite:{title:'À propos de cette démonstration',content:[shared.device,shared.contact,
    {question:'Une identité de démonstration',answer:'Les informations du restaurant sont configurables par son équipe. En mode démonstration, elles sont fictives et les visuels sont illustratifs. Le paiement est soit simulé, soit réalisé avec Stripe en mode test. Aucun paiement réel n’est activé.'},
  ]},
}:{
  questions:{title:'Une question ? On vous répond.',content:[shared.order,
    {question:'Quels sont les délais ?',answer:`${delays}, selon l’affluence.`},
    {question:'Comment suivre ma commande ?',answer:'Le statut est mis à jour par l’équipe du restaurant dans « Commandes ». L’e-mail de confirmation contient aussi un lien de suivi personnel.'},
  ]},
  allergenes:{title:'Allergènes & préférences',content:[
    {question:'Avant de choisir votre plat',answer:'Les allergènes renseignés par le restaurant sont indiqués dans le détail de chaque plat.'},
    {question:'Vous avez une allergie ?',answer:'Contactez le restaurant avant de commander : des traces peuvent être présentes même lorsqu’un allergène n’est pas indiqué.'},
    shared.veggie,
  ]},
  confidentialite:{title:'Vos données',content:[shared.device,shared.contact]},
};}
export function Footer({onNavigate,settings}:{onNavigate:(view:View)=>void;settings:RestaurantSettings|null}) {
  const [info,setInfo]=useState<Info|null>(null);
  const close=useCallback(()=>setInfo(null),[]);
  const demo=settings?.demoMode!==false;
  const details=information(demo,settings);
  return <>
    <footer className="site-footer" aria-label="Informations STC">
      <div className="footer-shell">
        <div className="footer-invitation">
          <div><span className="footer-eyebrow"><Flame size={14}/> LE PLAISIR, ÇA SE PARTAGE.</span><h2>On remet ça <span>?</span></h2><p>Du croustillant. De la générosité. Et vous.</p></div>
          <button className="footer-order" onClick={()=>onNavigate('Carte')}>Découvrir la carte <ArrowRight size={17}/></button>
        </div>
        <div className="footer-columns">
          <div className="footer-identity"><button className="footer-wordmark" aria-label="STC — Revenir à l’accueil" onClick={()=>onNavigate('Accueil')}>{settings?.name||restaurant.name}<span>®</span></button><p>{restaurant.tagline}</p><div className="footer-service-tags"><span><ShoppingBag size={13}/> À emporter</span><span><Truck size={14}/> Livraison</span></div></div>
          <div className="footer-location"><h3><MapPin size={15}/> La bonne adresse</h3><address>{settings?<>{settings.address}{' · '}<br/>{settings.city}</>:'…'}</address>{demo&&<span className="footer-demo-address">Adresse de démonstration</span>}</div>
          <div className="footer-hours"><h3><Clock size={15}/> À l’heure des envies</h3><p>{settings?.days||'…'}</p><strong>{settings?.hours||''}</strong>{demo&&<span className="footer-demo-address">Horaires indicatifs</span>}</div>
          <nav className="footer-links" aria-label="Liens utiles"><h3>Un petit raccourci</h3><button onClick={()=>onNavigate('Favoris')}>Mes favoris <Heart size={13}/></button><button onClick={()=>onNavigate('Commandes')}>Mes commandes <ArrowRight size={13}/></button><button onClick={()=>setInfo('questions')}>Questions fréquentes <ArrowRight size={13}/></button><button onClick={()=>setInfo('allergenes')}>Infos allergènes <ArrowRight size={13}/></button></nav>
        </div>
        <div className="footer-bottom"><span>© {new Date().getFullYear()} {settings?.name||'STC'} · Fait avec appétit.</span><button onClick={()=>setInfo('confidentialite')}>{demo?'Confidentialité & démo':'Confidentialité'}</button><button className="footer-top" onClick={()=>window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})} aria-label="Revenir en haut de la page"><ArrowUp size={15}/></button></div>
      </div>
    </footer>
    {info&&<Modal title={details[info].title} onClose={close}><div className="footer-info-modal"><span className="small-label">{settings?.name||restaurant.name} · LES INFOS UTILES</span><h2>{details[info].title}</h2>{details[info].content.map(item=><section key={item.question}><h3>{item.question}</h3><p>{item.answer}</p></section>)}<button className="primary full" onClick={close}>C’est compris</button></div></Modal>}
  </>;
}
