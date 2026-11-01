import {useEffect,useRef,type ReactNode} from 'react';
import {X} from 'lucide-react';

const modalStack:HTMLDivElement[]=[];
let unlockedOverflow='';
function updateModalStack(){
  const top=modalStack[modalStack.length-1];
  for(const modal of modalStack){
    const active=modal===top;
    modal.inert=!active;
    modal.setAttribute('aria-modal',String(active));
    if(active)modal.removeAttribute('aria-hidden');
    else modal.setAttribute('aria-hidden','true');
  }
}

export function Modal({children,title,onClose,wide=false}:{children:ReactNode;title:string;onClose:()=>void;wide?:boolean}){
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const el=ref.current;
    if(!el)return;
    const previous=document.activeElement as HTMLElement|null;
    if(!modalStack.length)unlockedOverflow=document.body.style.overflow;
    modalStack.push(el);
    updateModalStack();
    const focusable=()=>Array.from(el.querySelectorAll<HTMLElement>('button,input,select,textarea,a[href],[tabindex]'))
      .filter(node=>!node.matches(':disabled')&&!node.closest('[inert]')&&node.tabIndex>=0
        &&node.getClientRects().length>0&&getComputedStyle(node).visibility!=='hidden');
    document.body.style.overflow='hidden';
    el.focus();
    const keepFocus=(event:FocusEvent)=>{
      if(modalStack[modalStack.length-1]!==el)return;
      if(event.target instanceof Node&&!el.contains(event.target)){
        (focusable()[0]||el).focus();
      }
    };
    const handler=(event:KeyboardEvent)=>{
      if(modalStack[modalStack.length-1]!==el)return;
      if(event.key==='Escape')onClose();
      if(event.key!=='Tab')return;
      const nodes=focusable();
      if(!nodes.length){event.preventDefault();el.focus();return;}
      const first=nodes[0],last=nodes[nodes.length-1];
      const active=document.activeElement;
      // A field can become disabled while a request is in flight.
      if(!nodes.includes(active as HTMLElement)){
        event.preventDefault();(event.shiftKey?last:first).focus();
      }else if(event.shiftKey&&active===first){
        event.preventDefault();last.focus();
      }else if(!event.shiftKey&&active===last){
        event.preventDefault();first.focus();
      }
    };
    document.addEventListener('keydown',handler);
    document.addEventListener('focusin',keepFocus);
    return()=>{
      document.removeEventListener('keydown',handler);
      document.removeEventListener('focusin',keepFocus);
      const index=modalStack.indexOf(el);
      if(index>=0)modalStack.splice(index,1);
      updateModalStack();
      const top=modalStack[modalStack.length-1];
      document.body.style.overflow=top?'hidden':unlockedOverflow;
      if(previous?.isConnected&&(!top||top.contains(previous)))previous.focus();
      else top?.focus();
    };
  },[onClose]);
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide?'wide':''}`}>
      <button className="modal-close icon-button" aria-label="Fermer" onClick={onClose}><X size={20}/></button>{children}
    </div>
  </div>;
}
