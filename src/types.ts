// Categories are managed in the administration; 'Tout' is the catalogue-wide filter.
export type Category = string;
export interface CategoryInfo {name:string;position:number}
export interface OptionChoice {id:string;name:string;price:number}
export interface OptionGroup {id:string;name:string;min:number;max:number;choices:OptionChoice[]}
export interface Product {
  id:number; name:string; category:Category; description:string; summary?:string;
  price:number; regularPrice?:number; discountPercent?:number; image:string; badge?:string; rating?:string; options?:boolean;
  vegetarian?:boolean; available?:boolean; promotional?:boolean; allergens?:string[];
  optionGroups?:OptionGroup[];
}
export interface CartItem {
  key:string; product:Product; quantity:number; choices:string[]; choiceNames:string[];
  unitPrice:number; issue?:string;
  // Only used when migrating the first demonstration's stored basket.
  option?:string; extras?:string[];
}
export interface RestaurantSettings {
  name:string;address:string;city:string;hours:string;days:string;
  deliveryFee:number;minDeliveryTotal:number;deliveryPostalCodes:string[];
  orderingEnabled:boolean;isOpen:boolean;demoMode:boolean;paymentMode:'simulation'|'stripe';pickupEnabled?:boolean;deliveryEnabled?:boolean;pickupDelay?:string;deliveryDelay?:string;
}
export type OrderStatus='pending_payment'|'confirmed'|'preparing'|'ready'|'completed'|'cancelled';
export type PaymentStatus='simulated'|'pending'|'paid'|'failed'|'cancelled'|'refunded';
export interface Order {
  id:string;date:string;total:number;subtotal:number;deliveryFee:number;mode:string;
  items:string[];status:OrderStatus;paymentStatus:PaymentStatus;accessToken?:string;demoMode:boolean;
  lines:{name:string;quantity:number;unitPrice:number;total:number;choices:string[]}[];
  history:{status:OrderStatus;date:string}[];
  customer?:Customer;
}
export interface GuestOrderRef {id:string;accessToken:string}
export interface User {id:number;name:string;email:string}
export interface Customer {name:string;email:string;phone:string;address?:string;postal?:string;city?:string;note?:string}
export interface Address {id:number;label:string;name:string;phone:string;address:string;postal:string;city:string}
export interface OrderPayload {
  mode:'À emporter'|'Livraison';items:{productId:number;quantity:number;choices:string[]}[];
  customer:Customer;paymentMethod:'simulation'|'stripe';
}
export const euro=(n:number)=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(n);
export const cents=(n:number)=>Math.round(n*100);
export const money=(n:number)=>Math.round(n*100)/100;
export const statusLabels:Record<OrderStatus,string>={pending_payment:'En attente de paiement',confirmed:'Confirmée',preparing:'En cuisine',ready:'Prête à déguster',completed:'Terminée',cancelled:'Annulée'};
