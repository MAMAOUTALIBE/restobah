export function redirectToPayment(url:string){
  const target=new URL(url);
  if(target.protocol!=='https:'||target.hostname!=='checkout.stripe.com')throw new Error('Le lien de paiement reçu n’est pas valide. Veuillez réessayer.');
  window.location.assign(target.href);
}
/** Clear only the checkout attempt associated with this terminal order. */
export function forgetCheckoutForOrder(orderId:string){
  try{
    const saved=JSON.parse(sessionStorage.getItem('stc-payment-cart')||'null') as {id?:string}|null;
    if(saved?.id===orderId){sessionStorage.removeItem('stc-payment-cart');sessionStorage.removeItem('stc-checkout-key');}
  }catch{/* Storage is optional. */}
}
