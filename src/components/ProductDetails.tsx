import {useState} from 'react';
import {Plus,Minus,ShoppingBag,Check} from 'lucide-react';
import type {Product,CartItem} from '../types';
import {cents,euro} from '../types';
import {cartKey} from '../store/useCart';
import {FoodImage} from './FoodImage';
import {Modal} from './Modal';

export function ProductDetails({product:p,onClose,onAdd}:{product:Product;onClose:()=>void;onAdd:(i:CartItem)=>void}){
  const [choices,setChoices]=useState<string[]>([]);
  const [quantity,setQuantity]=useState(1);
  const [invalid,setInvalid]=useState<string[]>([]);
  const groups=p.optionGroups||[];
  const selected=groups.flatMap(g=>g.choices).filter(c=>choices.includes(c.id));
  const unit=(cents(p.price)+selected.reduce((total,c)=>total+cents(c.price),0))/100;
  const available=p.available!==false;
  function toggle(groupId:string,id:string){
    const group=groups.find(g=>g.id===groupId)!;
    setInvalid(old=>old.filter(key=>key!==groupId));
    setChoices(old=>{
      if(group.max===1)return [...old.filter(c=>!group.choices.some(choice=>choice.id===c)),id];
      return old.includes(id)?old.filter(c=>c!==id):[...old,id];
    });
  }
  return <Modal title={p.name} onClose={onClose}>
    <FoodImage className="detail-image" image={p.image} alt={p.name}/>
    <div className="detail-body"><span className="small-label">PRÉPARÉ À LA COMMANDE</span><h2>{p.name}</h2><p className="muted">{p.description}</p>
      {!available&&<p className="error" role="status">Ce plat est temporairement indisponible.</p>}
      <form onSubmit={e=>{e.preventDefault();const currentChoices=selected.map(choice=>choice.id).sort();setChoices(currentChoices);const errors=groups.filter(g=>{const count=g.choices.filter(c=>currentChoices.includes(c.id)).length;return count<g.min||count>g.max;}).map(g=>g.id);setInvalid(errors);if(errors.length||!available)return;onAdd({key:cartKey(p.id,currentChoices),product:p,quantity,choices:currentChoices,choiceNames:selected.map(c=>c.name),unitPrice:unit});onClose();}}>
        {groups.map(group=>{
          const checkedCount=group.choices.filter(c=>choices.includes(c.id)).length;
          return <fieldset key={group.id} aria-describedby={invalid.includes(group.id)?`error-${group.id}`:undefined}>
            <legend>{group.name} <span>{group.min>0?'Obligatoire':'Facultatif'}{group.max>1?` · ${group.max} max.`:''}</span></legend>
            {group.choices.map(choice=><label className="option" key={choice.id}>
              <input type={group.max===1?'radio':'checkbox'} name={`group-${group.id}`} value={choice.id} checked={choices.includes(choice.id)} disabled={!choices.includes(choice.id)&&group.max>1&&checkedCount>=group.max} onChange={()=>toggle(group.id,choice.id)}/>
              {choice.name}<span>{choice.price>0?`+ ${euro(choice.price)}`:'Inclus'}</span>
            </label>)}
            {group.min===0&&group.max===1&&checkedCount>0&&<button type="button" className="text-button" onClick={()=>setChoices(old=>old.filter(id=>!group.choices.some(c=>c.id===id)))}>Sans cette option</button>}
            {invalid.includes(group.id)&&<p id={`error-${group.id}`} className="error" role="alert">{group.min===1?'Sélectionnez une option pour continuer.':`Sélectionnez entre ${group.min} et ${group.max} options.`}</p>}
          </fieldset>;
        })}
        <div className="detail-actions"><div className="quantity"><button type="button" aria-label="Réduire la quantité" disabled={quantity===1} onClick={()=>setQuantity(quantity-1)}><Minus size={16}/></button><span>{quantity}</span><button type="button" aria-label="Augmenter la quantité" disabled={quantity>=20} onClick={()=>setQuantity(quantity+1)}><Plus size={16}/></button></div><button className="primary" disabled={!available} type="submit"><ShoppingBag size={17}/>Ajouter · {euro(unit*quantity)}</button></div>
        <p className="detail-note"><Check size={13}/> {Array.isArray(p.allergens)&&p.allergens.length?`Allergènes : ${p.allergens.join(', ')}.`:'Pour toute allergie, contactez le restaurant avant de commander.'}</p>
      </form>
    </div>
  </Modal>;
}
