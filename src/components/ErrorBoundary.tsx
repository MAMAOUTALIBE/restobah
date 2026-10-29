import {Component,type ReactNode} from 'react';
/** Last-resort screen: a display error must never leave a blank page; the basket stays in local storage. */
export class ErrorBoundary extends Component<{children:ReactNode},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(error:unknown){console.error('Erreur d’affichage STC',error);}
  render(){return this.state.failed?<main><div className="empty" role="alert"><h3>Un problème d’affichage est survenu.</h3><p>Votre panier est conservé sur cet appareil. Rechargez la page pour continuer.</p><button className="primary" onClick={()=>window.location.reload()}>Recharger la page</button></div></main>:this.props.children;}
}
