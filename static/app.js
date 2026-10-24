document.addEventListener("DOMContentLoaded",function(){
  var reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Animated stat counters
  document.querySelectorAll("[data-count]").forEach(function(el){
    var target=parseInt(el.dataset.count,10)||0;
    if(reduced||target===0){el.textContent=target;return;}
    var start=performance.now();
    function tick(now){var p=Math.min((now-start)/700,1);
      el.textContent=Math.round(target*(1-Math.pow(1-p,3)));
      if(p<1)requestAnimationFrame(tick);}
    requestAnimationFrame(tick);
  });
  // Live table search
  document.querySelectorAll("[data-filter]").forEach(function(input){
    var table=document.querySelector(input.dataset.filter);
    if(!table)return;
    input.addEventListener("input",function(){
      var q=input.value.toLowerCase();
      table.querySelectorAll("tbody tr").forEach(function(row){
        row.style.display=row.textContent.toLowerCase().indexOf(q)>-1?"":"none";
      });
    });
  });
  // Password show/hide
  document.querySelectorAll("[data-toggle-pw]").forEach(function(btn){
    btn.addEventListener("click",function(){
      var inp=document.querySelector(btn.dataset.togglePw);
      if(!inp)return;var showing=inp.type==="text";
      inp.type=showing?"password":"text";btn.textContent=showing?"Show":"Hide";
    });
  });
  // Live clock
  var clock=document.getElementById("clock");
  if(clock){function u(){clock.textContent=new Date().toLocaleTimeString("en-KE",{hour12:false});}u();setInterval(u,1000);}
  // Auto-dismiss flashes
  document.querySelectorAll(".alert-dismissible").forEach(function(a){
    setTimeout(function(){if(window.bootstrap)bootstrap.Alert.getOrCreateInstance(a).close();},6000);
  });
});
