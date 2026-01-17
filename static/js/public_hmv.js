(() => {
  const burger = document.getElementById("burgerBtn");
  const navMobile = document.getElementById("navMobile");
  const header = document.querySelector(".nav");
  const desktopLinks = Array.from(document.querySelectorAll(".nav-links a"));
  const mobileLinks = navMobile ? Array.from(navMobile.querySelectorAll("a[href^='#']")) : [];

  if (!burger || !navMobile) return;

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function isOpen() {
    return burger.getAttribute("aria-expanded") === "true" && navMobile.hidden === false;
  }

  function closeMenu() {
    if (navMobile.hidden) return;
    navMobile.hidden = true;
    burger.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    if (!navMobile.hidden) return;
    navMobile.hidden = false;
    burger.setAttribute("aria-expanded", "true");
  }

  function toggleMenu() {
    if (isOpen()) closeMenu();
    else openMenu();
  }

  // --- Menu interactions ---
  burger.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMenu();
  });

  // Cierra al dar click en links del menú móvil
  navMobile.addEventListener("click", (e) => {
    const a = e.target.closest("a");
    if (a) closeMenu();
  });

  // Cierra con ESC
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
  });

  // Cierra al hacer click fuera (fuera del header/nav)
  document.addEventListener("click", (e) => {
    if (!isOpen()) return;
    const insideHeader = header && header.contains(e.target);
    if (!insideHeader) closeMenu();
  });

  // Cierra si el usuario scrollea (pero sin ser agresivo)
  let scrollCloseTicking = false;
  window.addEventListener("scroll", () => {
    if (!isOpen()) return;
    if (scrollCloseTicking) return;
    scrollCloseTicking = true;
    window.requestAnimationFrame(() => {
      closeMenu();
      scrollCloseTicking = false;
    });
  }, { passive: true });

  // Si cambia a desktop, cerramos menú (evita estado raro)
  const mqDesktop = window.matchMedia("(min-width: 840px)");
  mqDesktop.addEventListener("change", () => {
    if (mqDesktop.matches) closeMenu();
  });

  // --- Active section highlighting (desktop + mobile) ---
  const sectionIds = [
    "inicio",
    "servicios",
    "especialidades",
    "instalaciones",
    "directorio",
    "contacto",
  ];

  const sections = sectionIds
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  function setActive(id) {
    // Desktop
    desktopLinks.forEach((a) => {
      const href = a.getAttribute("href");
      a.classList.toggle("is-active", href === `#${id}`);
      a.setAttribute("aria-current", href === `#${id}` ? "page" : "false");
    });

    // Mobile
    mobileLinks.forEach((a) => {
      const href = a.getAttribute("href");
      a.classList.toggle("is-active", href === `#${id}`);
      a.setAttribute("aria-current", href === `#${id}` ? "page" : "false");
    });
  }

  // Scroll spy con IntersectionObserver (más fino y pro)
  if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        // Elegimos la sección más visible
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

        if (visible && visible.target && visible.target.id) {
          setActive(visible.target.id);
        }
      },
      {
        root: null,
        threshold: [0.12, 0.2, 0.35, 0.5, 0.65],
        // offset para que active antes de estar totalmente al centro
        rootMargin: "-20% 0px -65% 0px",
      }
    );

    sections.forEach((sec) => observer.observe(sec));
  } else {
    // Fallback simple por si no hay IO
    const onScroll = () => {
      const y = window.scrollY + 120;
      let current = sections[0]?.id || "inicio";
      for (const sec of sections) {
        if (sec.offsetTop <= y) current = sec.id;
      }
      setActive(current);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // --- Smooth scroll mejorado (respeta reduced motion) ---
  // Solo para links internos
  const allAnchorLinks = [
    ...desktopLinks,
    ...mobileLinks,
    ...Array.from(document.querySelectorAll("a[href^='#']")),
  ];

  allAnchorLinks.forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#" || !href.startsWith("#")) return;

      const target = document.querySelector(href);
      if (!target) return;

      // Si el browser ya hace smooth con CSS, esto igual ayuda a controlar offset
      e.preventDefault();

      const headerOffset = header ? header.offsetHeight + 10 : 80;
      const rect = target.getBoundingClientRect();
      const top = window.pageYOffset + rect.top - headerOffset;

      window.scrollTo({
        top,
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });

      // activa manualmente para que se sienta inmediato
      if (target.id) setActive(target.id);
    }, { passive: false });
  });
})();
