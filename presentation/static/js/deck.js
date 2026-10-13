/* ═══════════════════════════════════════════════════════════════
   Flask Press — deck runtime

   Reveal init · lightbox · auto-fit · presenter navigation
   · optional: constellation cover, animated counters, typewriter

   Everything below is generic. Deck-specific animation goes at the
   bottom, inside enter()/leave(). See pitfalls.md before changing
   the Reveal config or the measurement code.
   ═══════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    /* ── Reveal ─────────────────────────────────────────────── */
    Reveal.initialize({
        hash: true,
        slideNumber: 'c/t',
        progress: true,
        center: false,              // NEVER true — collides with the header budget
        width: 1280,
        height: 720,
        margin: 0.04,
        transition: 'slide',
        transitionSpeed: 'default',
        backgroundTransition: 'fade',

        // LOAD-BEARING. Reveal writes `display` as an INLINE style on every
        // shown slide, which beats any stylesheet rule. The deck is a flex
        // column, so it MUST be set here — `display:flex` in CSS alone is
        // silently ignored and the column layout quietly does nothing.
        display: 'flex',
        pdfSeparateFragments: false,

        autoAnimateEasing: 'cubic-bezier(0.2, 0.8, 0.3, 1)',
        autoAnimateDuration: 0.7,
        plugins: [RevealHighlight, RevealNotes, RevealZoom]
    });

    /* ── Lightbox ───────────────────────────────────────────── */
    var lb = document.getElementById('lightbox');
    var lbImg = document.getElementById('lightbox-img');

    window.openLightbox = function (img) {
        lbImg.src = img.src;
        lb.classList.add('active');
    };
    window.closeLightbox = function () { lb.classList.remove('active'); };

    /* ── Auto-fit ───────────────────────────────────────────────
       Safety net. If a slide's content is taller than the 720px canvas
       (a title wrapped to two lines, a dense grid, a translated string
       that ran long), shrink that slide's body instead of letting it
       spill. Pass `data-nofit` on a .slide-body to opt out — needed
       when it contains an absolutely-positioned canvas.              */
    function fitSlide(slide) {
        var body = slide.querySelector('.slide-body');
        if (!body || body.hasAttribute('data-nofit')) return;

        var kids = body.children;
        if (!kids.length) return;

        body.style.setProperty('--fit', 1);
        body.removeAttribute('data-fit');

        // Sum what each child NEEDS, not the box it was squeezed into.
        // A grid child carries min-height:0, so when its rows don't fit the
        // flex track it keeps its short box and spills its rows over the
        // neighbours — measuring first-child-top to last-child-bottom reads
        // that as "fits" while the slide is visibly overlapping.
        // scrollHeight sees the real content.
        //
        // All layout px (offsetHeight/clientHeight), NEVER
        // getBoundingClientRect — Reveal's scaling transform inflates that.
        var gap = parseFloat(getComputedStyle(body).rowGap) || 0;
        var need = 0;
        for (var i = 0; i < kids.length; i++) {
            need += Math.max(kids[i].offsetHeight, kids[i].scrollHeight);
            if (i) need += gap;
        }

        var avail = body.clientHeight;
        if (avail > 0 && need > avail + 2) {
            var scale = Math.max(0.62, (avail - 2) / need);
            body.style.setProperty('--fit', scale.toFixed(4));
            body.setAttribute('data-fit', '');
        }
    }

    /* ═══════════════════════════════════════════════════════════
       PRESENTER NAVIGATION
       Three arrow-free ways through the deck: Space (Reveal's own),
       clicking the screen margin, and a jump menu on M.
       ═══════════════════════════════════════════════════════════ */
    var navMenu  = document.getElementById('nav-menu');
    var navList  = document.getElementById('nav-list');
    var helpCard = document.getElementById('help-card');

    function esc(s) {
        return s.replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }

    function modalOpen() {
        return navMenu.classList.contains('active') || helpCard.classList.contains('active');
    }
    function closeModals() {
        navMenu.classList.remove('active');
        helpCard.classList.remove('active');
        Reveal.configure({ keyboard: true });     // hand the keyboard back
    }
    function openModal(el) {
        navMenu.classList.remove('active');
        helpCard.classList.remove('active');
        el.classList.add('active');
        // otherwise Space advances the slide behind the overlay
        Reveal.configure({ keyboard: false });
    }

    function buildNavList() {
        var secs = Reveal.getHorizontalSlides();
        var html = '', group = '';
        secs.forEach(function (sec, i) {
            var marker = sec.querySelector('.act');
            // A slide may drop its .act marker (e.g. a full-bleed visual);
            // carry the previous group forward rather than orphaning it.
            var g = i === 0 ? 'Apertura'
                  : i === secs.length - 1 ? 'Cierre'
                  : marker ? marker.textContent.trim() : group;
            if (g !== group) {
                html += '<div class="nav-act">' + esc(g) + '</div>';
                group = g;
            }
            var h = sec.querySelector('h1, h2, .q-text');
            var title = 'Lámina ' + (i + 1);
            if (h) {
                // clone first: textContent welds "Two<br>Words" into "TwoWords"
                var c = h.cloneNode(true);
                c.querySelectorAll('br').forEach(function (br) {
                    br.replaceWith(document.createTextNode(' '));
                });
                title = c.textContent.replace(/\s+/g, ' ').trim();
            }
            var deep = sec.querySelectorAll('section').length > 1
                ? '<span class="sub">&darr; a fondo</span>' : '';
            html += '<button data-i="' + i + '"><span class="n">' + (i + 1) + '</span>' +
                    '<span>' + esc(title) + deep + '</span></button>';
        });
        navList.innerHTML = html;
        navList.querySelectorAll('button').forEach(function (b) {
            b.addEventListener('click', function () {
                closeModals();
                Reveal.slide(parseInt(b.dataset.i, 10), 0);
            });
        });
    }

    function markCurrent() {
        var idx = Reveal.getIndices().h;
        navList.querySelectorAll('button').forEach(function (b) {
            b.classList.toggle('current', parseInt(b.dataset.i, 10) === idx);
        });
    }

    function toggleMenu() {
        if (navMenu.classList.contains('active')) { closeModals(); return; }
        markCurrent();
        openModal(navMenu);
    }
    function toggleHelp() {
        if (helpCard.classList.contains('active')) { closeModals(); return; }
        openModal(helpCard);
    }

    var edgePrev = document.getElementById('edge-prev');
    var edgeNext = document.getElementById('edge-next');
    edgePrev.addEventListener('click', function () { Reveal.prev(); });
    edgeNext.addEventListener('click', function () { Reveal.next(); });
    document.getElementById('nav-fab').addEventListener('click', toggleMenu);

    function syncEdges() {
        edgePrev.classList.toggle('disabled', Reveal.isFirstSlide());
        edgeNext.classList.toggle('disabled', Reveal.isLastSlide());
    }

    [navMenu, helpCard].forEach(function (m) {
        m.addEventListener('click', function (e) { if (e.target === m) closeModals(); });
    });

    // Capture phase, so these land before Reveal's own document handler
    // (otherwise Esc would also toggle overview behind the modal).
    document.addEventListener('keydown', function (e) {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        var t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;

        if (e.key === 'Escape') {
            if (lb.classList.contains('active')) { window.closeLightbox(); }
            else if (modalOpen()) { closeModals(); }
            else { return; }
        } else if (e.key === 'm' || e.key === 'M') {
            toggleMenu();
        } else if (e.key === '?') {
            toggleHelp();
        } else {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
    }, true);

    /* ═══════════════════════════════════════════════════════════
       OPTIONAL EFFECTS — delete what the deck does not use
       ═══════════════════════════════════════════════════════════ */

    /* Animated counters — <span class="num" data-count-to="186">0</span>
       Optional: data-count-suffix="%"  data-count-dur="1400"          */
    function runCounters(scope) {
        scope.querySelectorAll('[data-count-to]').forEach(function (el) {
            if (el.dataset.counted === '1') return;
            el.dataset.counted = '1';
            var to = parseFloat(el.dataset.countTo);
            var dur = parseInt(el.dataset.countDur || '1100', 10);
            var suffix = el.dataset.countSuffix || '';
            var prefix = el.dataset.countPrefix || '';
            var dec = (String(to).split('.')[1] || '').length;
            var t0 = null;
            function tick(ts) {
                if (t0 === null) t0 = ts;
                var p = Math.min((ts - t0) / dur, 1);
                var e = 1 - Math.pow(1 - p, 3);                  // easeOutCubic
                var v = to * e;
                el.textContent = prefix + (dec ? v.toFixed(dec)
                                      : Math.round(v).toLocaleString('en-US')) + suffix;
                if (p < 1) requestAnimationFrame(tick);
            }
            el.textContent = prefix + '0' + suffix;
            requestAnimationFrame(tick);
        });
    }
    // Printed or exported to PDF there is no animation: write the final value.
    if (/print-pdf/.test(window.location.search)) {
        document.querySelectorAll('[data-count-to]').forEach(function (el) {
            var to = parseFloat(el.dataset.countTo);
            var dec = (String(to).split('.')[1] || '').length;
            el.dataset.counted = '1';
            el.textContent = (el.dataset.countPrefix || '') +
                (dec ? to.toFixed(dec) : to.toLocaleString('en-US')) + (el.dataset.countSuffix || '');
        });
    }
    function resetCounters(scope) {
        scope.querySelectorAll('[data-count-to]').forEach(function (el) { el.dataset.counted = '0'; });
    }

    /* Typewriter — <p data-type="text that types itself out"></p>
       Put data-type on the element that should hold ONLY the typed text:
       typeOut clears textContent, so a sibling label inside the same
       element would be wiped.                                          */
    function typeOut(el) {
        if (el.dataset.typed === '1') return;
        el.dataset.typed = '1';
        var full = el.dataset.type || '';
        el.textContent = '';
        var caret = document.createElement('span');
        caret.className = 'caret';
        el.appendChild(caret);
        var i = 0;
        (function step() {
            if (i <= full.length) {
                caret.remove();
                el.textContent = full.slice(0, i);
                el.appendChild(caret);
                i++;
                setTimeout(step, 16 + Math.random() * 22);
            } else {
                setTimeout(function () { caret.remove(); }, 900);
            }
        })();
    }

    /* Constellation — <canvas class="constellation"></canvas> on a cover */
    function constellation(canvas) {
        var ctx = canvas.getContext('2d');
        var pts = [], raf = null, running = false;
        var W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);

        function size() {
            var r = canvas.getBoundingClientRect();
            W = r.width || 1280; H = r.height || 720;
            canvas.width = W * DPR; canvas.height = H * DPR;
            ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        }
        function seed() {
            pts = [];
            var n = Math.round((W * H) / 15000);
            for (var i = 0; i < n; i++) {
                pts.push({
                    x: Math.random() * W, y: Math.random() * H,
                    vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
                    r: Math.random() * 1.7 + 0.9
                });
            }
        }
        function frame() {
            if (!running) return;
            ctx.clearRect(0, 0, W, H);
            for (var i = 0; i < pts.length; i++) {
                var p = pts[i];
                p.x += p.vx; p.y += p.vy;
                if (p.x < 0 || p.x > W) p.vx *= -1;
                if (p.y < 0 || p.y > H) p.vy *= -1;
            }
            for (var a = 0; a < pts.length; a++) {
                for (var b = a + 1; b < pts.length; b++) {
                    var dx = pts[a].x - pts[b].x, dy = pts[a].y - pts[b].y;
                    var d2 = dx * dx + dy * dy;
                    if (d2 < 20000) {
                        ctx.strokeStyle = 'rgba(46,230,166,' + ((1 - d2 / 20000) * 0.32).toFixed(3) + ')';
                        ctx.lineWidth = 0.6;
                        ctx.beginPath();
                        ctx.moveTo(pts[a].x, pts[a].y);
                        ctx.lineTo(pts[b].x, pts[b].y);
                        ctx.stroke();
                    }
                }
            }
            for (var k = 0; k < pts.length; k++) {
                ctx.fillStyle = 'rgba(46,230,166,0.65)';
                ctx.beginPath();
                ctx.arc(pts[k].x, pts[k].y, pts[k].r, 0, Math.PI * 2);
                ctx.fill();
            }
            raf = requestAnimationFrame(frame);
        }
        size(); seed();
        return {
            start: function () { if (running) return; running = true; frame(); },
            stop:  function () { running = false; if (raf) cancelAnimationFrame(raf); },
            resize: function () { size(); seed(); }
        };
    }

    /* Unit grid — <div class="waffle" data-total="54" data-on="20"></div>
       draws `total` dots, the first `on` of them filled.                */
    document.querySelectorAll('.waffle[data-total]').forEach(function (w) {
        var total = parseInt(w.dataset.total, 10), on = parseInt(w.dataset.on, 10);
        var html = '';
        for (var i = 0; i < total; i++) html += '<i' + (i < on ? ' class="on"' : '') + '></i>';
        w.innerHTML = html;
    });

    var stars = [];
    document.querySelectorAll('canvas.constellation').forEach(function (c) {
        stars.push({ el: c, ctl: constellation(c) });
    });
    window.addEventListener('resize', function () {
        stars.forEach(function (s) { s.ctl.resize(); });
    });

    /* ── Slide lifecycle ────────────────────────────────────── */
    function enter(slide) {
        if (!slide) return;
        runCounters(slide);

        // Only type what is already on screen. Anything inside an unrevealed
        // fragment waits for 'fragmentshown', or it finishes typing behind an
        // invisible element and is fully written before the room sees it.
        slide.querySelectorAll('[data-type]').forEach(function (el) {
            var frag = el.closest('.fragment');
            if (!frag || frag.classList.contains('visible')) typeOut(el);
        });

        stars.forEach(function (s) {
            if (slide.contains(s.el)) { s.ctl.resize(); s.ctl.start(); }
            else s.ctl.stop();
        });

        // re-measure after fonts settle and highlighting lands
        requestAnimationFrame(function () { fitSlide(slide); });
        setTimeout(function () { fitSlide(slide); }, 260);
    }

    function leave(slide) {
        if (!slide) return;
        resetCounters(slide);
        slide.querySelectorAll('[data-type]').forEach(function (el) {
            el.dataset.typed = '0';
            el.textContent = '';
        });
    }

    Reveal.on('ready', function (e) {
        buildNavList();
        syncEdges();
        enter(e.currentSlide);
    });
    Reveal.on('slidechanged', function (e) {
        leave(e.previousSlide);
        enter(e.currentSlide);
        syncEdges();
    });
    Reveal.on('resize', function () {
        setTimeout(function () {
            var cur = Reveal.getCurrentSlide();
            if (cur) fitSlide(cur);
        }, 80);
    });
    Reveal.on('fragmentshown', function (e) {
        if (e.fragment.dataset.type) typeOut(e.fragment);
        e.fragment.querySelectorAll('[data-type]').forEach(typeOut);
    });
})();
