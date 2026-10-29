import type {Address,CategoryInfo,Order,OrderPayload,Product,RestaurantSettings,User} from '../types';

export class ApiError extends Error {
  constructor(message:string,public status:number,public errors?:unknown){super(message);this.name='ApiError';}
}
const csrfCookie=()=>document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.slice('csrftoken='.length);
let csrfRequest:Promise<void>|null=null;
async function ensureCsrf(force=false){
  if(!force&&csrfCookie())return;
  if(!csrfRequest){
    const controller=new AbortController();
    const timeout=window.setTimeout(()=>controller.abort(),20000);
    csrfRequest=fetch('/api/auth/csrf/',{credentials:'include',cache:'no-store',signal:controller.signal})
      .then(r=>{if(!r.ok)throw new ApiError('Impossible de sécuriser la connexion. Réessayez.',r.status);})
      .catch(error=>{if(error instanceof ApiError)throw error;throw new ApiError('Impossible de sécuriser la connexion. Vérifiez votre connexion puis réessayez.',0);})
      .finally(()=>{window.clearTimeout(timeout);csrfRequest=null;});
  }
  await csrfRequest;
}
function errorMessage(data:unknown):string {
  if(typeof data==='string')return data.slice(0,400);
  if(data&&typeof data==='object'){
    const record=data as Record<string,unknown>;
    if(typeof record.detail==='string')return record.detail;
    for(const [key,value] of Object.entries(record)){
      if(Array.isArray(value)&&typeof value[0]==='string')return `${key==='non_field_errors'?'':`${key} : `}${value[0]}`;
    }
  }
  return 'La demande n’a pas abouti. Veuillez réessayer.';
}
async function request<T>(path:string,options:RequestInit={}):Promise<T>{
  const writes=options.method&&options.method!=='GET';
  if(writes)await ensureCsrf(path==='/orders/');
  const controller=new AbortController();
  const timeout=window.setTimeout(()=>controller.abort(),20000);
  try{
    const headers=new Headers(options.headers);
    if(options.body)headers.set('Content-Type','application/json');
    if(writes){const csrf=csrfCookie();if(csrf)headers.set('X-CSRFToken',decodeURIComponent(csrf));}
    const response=await fetch(`/api${path}`,{...options,headers,credentials:'include',cache:'no-store',signal:controller.signal});
    const contentType=response.headers.get('content-type')||'';
    const data:unknown=response.status===204?undefined:contentType.includes('application/json')?await response.json():undefined;
    if(!response.ok)throw new ApiError(data?errorMessage(data):response.status===503?'Le service est temporairement indisponible. Réessayez dans un instant.':'La connexion au restaurant a échoué. Réessayez.',response.status,data);
    if(response.status!==204&&!contentType.includes('application/json'))throw new ApiError('Le service de commande est indisponible. Veuillez réessayer.',502);
    return data as T;
  }catch(error){
    if(error instanceof ApiError)throw error;
    throw new ApiError(error instanceof DOMException&&error.name==='AbortError'?'La connexion prend trop de temps. Votre panier est conservé ; réessayez.':'Connexion impossible. Vérifiez votre connexion et réessayez.',0);
  }finally{window.clearTimeout(timeout);}
}
const json=(method:string,body?:unknown):RequestInit=>({method,...(body===undefined?{}:{body:JSON.stringify(body)})});
export const restaurantApi={
  getProducts:()=>request<Product[]>('/products/'),
  getCategories:()=>request<CategoryInfo[]>('/categories/'),
  getRestaurant:()=>request<RestaurantSettings>('/restaurant/'),
  me:()=>request<{user:User|null}>('/auth/me/'),
  register:(data:{name:string;email:string;password:string})=>request<{user:User}>('/auth/register/',json('POST',data)),
  login:(data:{email:string;password:string})=>request<{user:User}>('/auth/login/',json('POST',data)),
  logout:()=>request<{detail:string}>('/auth/logout/',json('POST')),
  passwordReset:(email:string)=>request<{detail:string}>('/auth/password-reset/',json('POST',{email})),
  passwordConfirm:(data:{uid:string;token:string;password:string})=>request<{detail:string}>('/auth/password-reset-confirm/',json('POST',data)),
  deleteAccount:(password:string)=>request<{detail:string}>('/auth/delete-account/',json('POST',{password})),
  getAddresses:()=>request<Address[]>('/addresses/'),
  saveAddress:(address:Omit<Address,'id'>,id?:number)=>request<Address>(id?`/addresses/${id}/`:'/addresses/',json(id?'PATCH':'POST',address)),
  deleteAddress:(id:number)=>request<void>(`/addresses/${id}/`,json('DELETE')),
  getFavorites:()=>request<number[]>('/favorites/'),
  saveFavorites:(productIds:number[])=>request<number[]>('/favorites/',json('PUT',{productIds})),
  placeOrder:(payload:OrderPayload,key:string)=>request<Order>('/orders/',{...json('POST',payload),headers:{'Idempotency-Key':key}}),
  getOrders:()=>request<Order[]>('/orders/'),
  getOrder:(id:string,token?:string)=>request<Order>(`/orders/${encodeURIComponent(id)}/${token?`?token=${encodeURIComponent(token)}`:''}`),
  createPayment:(id:string,token?:string)=>request<{url:string}>(`/orders/${encodeURIComponent(id)}/payment/`,json('POST',token?{token}:{})),
};
export const messageOf=(error:unknown)=>error instanceof Error?error.message:'Une erreur est survenue. Réessayez.';
