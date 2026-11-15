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
