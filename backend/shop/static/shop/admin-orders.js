// Order list: reload every 30 s so new orders appear, unless the team is selecting rows or typing.
document.addEventListener('DOMContentLoaded',function(){
  if(!document.body.classList.contains('change-list'))return;
  window.setInterval(function(){
    var active=document.activeElement;
    var busy=document.querySelector('#result_list input.action-select:checked')||(active&&/^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName));
    if(!busy&&document.visibilityState==='visible')window.location.reload();
  },30000);
});
