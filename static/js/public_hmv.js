(function(){
    const burger = document.getElementById("burgerBtn");
    const navMobile = document.getElementById("navMobile");
  
    if(!burger || !navMobile) return;
  
    function closeMenu(){
      navMobile.hidden = true;
      burger.setAttribute("aria-expanded", "false");
    }
  
    function openMenu(){
      navMobile.hidden = false;
      burger.setAttribute("aria-expanded", "true");
    }
  
    burger.addEventListener("click", () => {
      const expanded = burger.getAttribute("aria-expanded") === "true";
      if(expanded) closeMenu();
      else openMenu();
    });
  
    // Cierra al dar click en links
    navMobile.addEventListener("click", (e) => {
      const a = e.target.closest("a");
      if(a) closeMenu();
    });
  
    // Cierra con ESC
    window.addEventListener("keydown", (e) => {
      if(e.key === "Escape") closeMenu();
    });
  })();
  