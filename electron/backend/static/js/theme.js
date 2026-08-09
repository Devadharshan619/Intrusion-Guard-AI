// tiny theme hook; default dark. You can toggle by setting data-theme on <html>
(function(){
  const html = document.documentElement;
  if(!html.getAttribute('data-theme')) html.setAttribute('data-theme','dark');
})();
