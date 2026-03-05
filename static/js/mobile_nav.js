(function(){
  function qs(sel){ return document.querySelector(sel); }

  const openBtn = qs('[data-open-sidebar]');
  const closeBtn = qs('[data-close-sidebar]');
  const sidebar = qs('.app-sidebar');

  if(!sidebar) return;

  function open(){
    sidebar.classList.add('is-open');
    document.documentElement.style.overflow = 'hidden';
  }
  function close(){
    sidebar.classList.remove('is-open');
    document.documentElement.style.overflow = '';
  }

  openBtn && openBtn.addEventListener('click', open);
  closeBtn && closeBtn.addEventListener('click', close);

  sidebar.addEventListener('click', (e)=>{
    if(e.target === sidebar) close();
  });
})();