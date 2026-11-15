/* Erasmus+ · IC Pescara 6 — script unico, vanilla JS */
(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js");

  /* Header: bordo/sfondo dopo lo scroll */
  const header = $("[data-header]");
  if (header) {
    const onScroll = () => header.classList.toggle("scrolled", scrollY > 24);
    onScroll();
    addEventListener("scroll", onScroll, { passive: true });
  }

  /* Chiude un <dialog> cliccando sul backdrop */
  const closeOnBackdrop = (dialog) =>
    dialog.addEventListener("click", (ev) => { if (ev.target === dialog) dialog.close(); });

  /* Menu mobilità */
  const menu = $("[data-menu]");
  if (menu) {
    $$("[data-menu-open]").forEach((b) => b.addEventListener("click", () => menu.showModal()));
    $$("[data-menu-close]", menu).forEach((b) => b.addEventListener("click", () => menu.close()));
    closeOnBackdrop(menu);
    $$("a", menu).forEach((a) => a.addEventListener("click", () => menu.close()));
  }

  /* Comparsa progressiva degli elementi */
  const reveals = $$(".reveal");
  if ("IntersectionObserver" in window && !reducedMotion) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  /* Filtro per tipologia (home) */
  const chips = $$("[data-filter]");
  if (chips.length) {
    const empty = $("[data-empty]");
    chips.forEach((chip) => chip.addEventListener("click", () => {
      const f = chip.dataset.filter;
      chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
      let visible = 0;
      $$("[data-year]").forEach((year) => {
        let n = 0;
        $$(".card", year).forEach((card) => {
          const show = f === "all" || card.dataset.type === f;
          card.hidden = !show;
          if (show) { n++; card.classList.add("in"); }
        });
        year.hidden = n === 0;
        visible += n;
      });
      if (empty) empty.hidden = visible > 0;
    }));
  }

  /* Contatori animati (home) */
  const counters = $$("[data-count]");
  if (counters.length && !reducedMotion) {
    counters.forEach((el) => {
      const target = +el.dataset.count;
      const t0 = performance.now();
      const dur = 1100;
      const tick = (t) => {
        const p = Math.min(1, (t - t0) / dur);
        el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }

  /* Mappa: segnaposto con anteprima */
  const mapWrap = $("[data-map-wrap]");
  if (mapWrap) {
    const map = $("[data-map]", mapWrap);
    const pins = $$("[data-pin]", map);
    const canHover = matchMedia("(hover: hover)");

    const setOpen = (wrap, open) => {
      wrap.classList.toggle("open", open);
      const btn = $("button.pin", wrap);
      if (btn) btn.setAttribute("aria-expanded", String(open));
    };
    const closeAll = (except) => pins.forEach((w) => { if (w !== except) setOpen(w, false); });

    pins.forEach((wrap) => {
      const trigger = $(".pin", wrap);
      trigger.addEventListener("click", (ev) => {
        const isOpen = wrap.classList.contains("open");
        const isGroup = trigger.tagName === "BUTTON";
        // Con il mouse: clic sul segnaposto singolo = apre la pagina (l'anteprima è già visibile con l'hover).
        // Su touch: primo tocco = anteprima, secondo tocco sullo stesso segnaposto = apre la pagina.
        // Gruppi (più mobilità): il clic apre/chiude l'elenco.
        if (isGroup || (!canHover.matches && !isOpen)) {
          ev.preventDefault();
          closeAll(wrap);
          setOpen(wrap, !isOpen);
        }
      });
      const close = $("[data-pop-close]", wrap);
      if (close) close.addEventListener("click", (ev) => { ev.stopPropagation(); setOpen(wrap, false); });
    });
    document.addEventListener("click", (ev) => { if (!ev.target.closest("[data-pin]")) closeAll(); });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeAll(); });

    // Mobile: la mappa scorre in orizzontale. All'avvio la centro sulle mobilità
    // e nascondo il suggerimento "trascina" al primo scorrimento dell'utente.
    let autoScroll = false;
    const centerMap = () => {
      if (map.scrollWidth <= map.clientWidth) return;
      const focus = parseFloat(map.dataset.focus) || 0.5;
      autoScroll = true;
      map.scrollLeft = focus * map.scrollWidth - map.clientWidth / 2;
      requestAnimationFrame(() => { autoScroll = false; });
    };
    centerMap();
    addEventListener("load", centerMap, { once: true });
    setTimeout(() => mapWrap.classList.add("scrolled"), 4500);
    map.addEventListener("scroll", () => {
      if (autoScroll) return;
      mapWrap.classList.add("scrolled");
    }, { passive: true });

    // Dopo l'animazione di disegno le rotte diventano tratteggiate.
    const route = $(".map-route", map);
    if (route) route.addEventListener("transitionend", () => mapWrap.classList.add("drawn"), { once: true });
  }

  /* Lightbox galleria */
  const lb = $("[data-lightbox-dialog]");
  const links = $$("[data-lightbox]");
  if (lb && links.length) {
    const img = $("[data-lb-img]", lb);
    const caption = $("[data-lb-caption]", lb);
    let index = 0;

    const show = (i) => {
      index = (i + links.length) % links.length;
      const a = links[index];
      img.classList.add("loading");
      img.onload = () => img.classList.remove("loading");
      img.src = a.href;
      img.width = +a.dataset.w;
      img.height = +a.dataset.h;
      img.alt = $("img", a).alt;
      caption.textContent = `${index + 1} / ${links.length}`;
      // precarica la successiva
      const next = links[(index + 1) % links.length];
      if (next) { const pre = new Image(); pre.src = next.href; }
    };

    links.forEach((a, i) => a.addEventListener("click", (ev) => {
      ev.preventDefault();
      show(i);
      lb.showModal();
    }));
    $("[data-lb-prev]", lb).addEventListener("click", () => show(index - 1));
    $("[data-lb-next]", lb).addEventListener("click", () => show(index + 1));
    $("[data-lb-close]", lb).addEventListener("click", () => lb.close());
    lb.addEventListener("click", (ev) => { if (ev.target === lb || ev.target.tagName === "FIGURE") lb.close(); });
    lb.addEventListener("close", () => links[index].focus({ preventScroll: true }));
    lb.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft") show(index - 1);
      if (ev.key === "ArrowRight") show(index + 1);
    });

    // swipe su touch
    let x0 = null;
    lb.addEventListener("touchstart", (ev) => { x0 = ev.touches[0].clientX; }, { passive: true });
    lb.addEventListener("touchend", (ev) => {
      if (x0 === null) return;
      const dx = ev.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
      x0 = null;
    });
  }
})();
