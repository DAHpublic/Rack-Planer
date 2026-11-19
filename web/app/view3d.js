/* Rack-Planer Web – 3D-Ansicht im Browser.
 *
 * Gleiches Verfahren wie die 3D-Ansicht der Desktop-Version (planer2d/view3d.py): Der Schrank
 * besteht aus achsparallelen Quadern, die perspektivisch projiziert und von hinten nach vorne
 * gezeichnet werden (Maleralgorithmus mit Trennebenen) – mit dem normalen Canvas, ohne WebGL.
 * Läuft damit in jedem Browser, auch ohne Grafikkarte.
 *
 * Alle Regeln (belegte HE, Fachbodenhöhe, erlaubte Ziele beim Ziehen) liefert der Server in
 * view.scene3d und view.targets; hier werden nur Quader gebaut und gezeichnet.
 *
 * Koordinaten in mm: x nach rechts (von vorne gesehen), y nach oben, z nach vorne.
 * Die vordere Montageebene liegt bei z = +Tiefe/2, die hintere bei z = −Tiefe/2.
 */
"use strict";

const View3D = (() => {
  const U_MM = 44.45;
  const EAR_HALF = 241.3, BODY_HALF = 222.0;
  const PROFILE_IN = 224.0, PROFILE_OUT = 262.0, PROFILE_D = 20.0;
  const OUTER_HALF = 300.0, POST = 30.0, CAB_EXTRA = 70.0, TOP_H = 40.0, BASE_H = 40.0, PLINTH_H = 60.0;
  const EAR_D = 4.0, PLATE_H = 6.0, UNKNOWN_DEPTH = 40.0, EPS = 1e-6, NEAR = 20.0;
  const HOLE_X = 232.5, HOLE_SIZE = 9.5, HOLE_OFFSETS = [6.35, 6.35 + 15.875, 6.35 + 2 * 15.875];
  const ACCENT = "#e8800c", RED = "#e5413a", TEXT = "#ececec", MUTED = "#a9adb0";
  const FACES = [[0, 1], [0, -1], [1, 1], [1, -1], [2, 1], [2, -1]];
  const PRESETS = { front: [0, 6], rear: [180, 6], left: [-90, 4], right: [90, 4], top: [-20, 72], iso: [-32, 16] };
  const rad = (d) => d * Math.PI / 180;

  // --- Farben ------------------------------------------------------------------------
  function col(hex, a = 1) {
    const c = hex.replace("#", "");
    return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16), a];
  }
  const css = (c) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${c[3]})`;
  const shade = (c, f) => [Math.min(255, c[0] * f), Math.min(255, c[1] * f), Math.min(255, c[2] * f), c[3]];
  const mix = (a, b, t) => [a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t, a[2] * (1 - t) + b[2] * t, a[3]];
  const FRAME = col("#3b3e42"), FRAME_DARK = col("#2a2c2f"), PROFILE = col("#a9aeb2"), RAIL = col("#b9bec2");
  const PANEL = [150, 160, 170, 0.18], GHOST_OK = [46, 204, 113, 0.47], GHOST_BAD = [231, 76, 60, 0.47];

  // --- Vektoren ------------------------------------------------------------------------
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const n = Math.sqrt(dot(a, a)) || 1; return [a[0] / n, a[1] / n, a[2] / n]; };
  const dist3 = (a, b) => Math.sqrt(dot(sub(a, b), sub(a, b)));

  function faceCorners(lo, hi, axis, sign) {
    const [x0, y0, z0] = lo, [x1, y1, z1] = hi;
    if (axis === 2 && sign > 0) return [[x0, y1, z1], [x1, y1, z1], [x1, y0, z1], [x0, y0, z1]];
    if (axis === 2) return [[x1, y1, z0], [x0, y1, z0], [x0, y0, z0], [x1, y0, z0]];
    if (axis === 0 && sign > 0) return [[x1, y1, z1], [x1, y1, z0], [x1, y0, z0], [x1, y0, z1]];
    if (axis === 0) return [[x0, y1, z0], [x0, y1, z1], [x0, y0, z1], [x0, y0, z0]];
    if (axis === 1 && sign > 0) return [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]];
    return [[x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0]];
  }
  function faceSize(lo, hi, axis) {
    const dx = hi[0] - lo[0], dy = hi[1] - lo[1], dz = hi[2] - lo[2];
    return axis === 2 ? [dx, dy] : axis === 0 ? [dz, dy] : [dx, dz];
  }

  function box(lo, hi, color, o = {}) {
    return { lo, hi, color, uid: o.uid || "", outline: o.outline || null, ow: o.ow ?? 0.8,
             decor: o.decor || {}, shade: o.shade !== false, polys: [], rect: null, hull: null, dist: 0 };
  }
  const center = (b) => [(b.lo[0] + b.hi[0]) / 2, (b.lo[1] + b.hi[1]) / 2, (b.lo[2] + b.hi[2]) / 2];

  // --- Kamera --------------------------------------------------------------------------
  function camera() { return { target: [0, 0, 0], yaw: rad(-32), pitch: rad(16), dist: 3000, fov: rad(35) }; }
  const copyCam = (c) => ({ ...c, target: [...c.target] });
  function camPos(c) {
    const cp = Math.cos(c.pitch), t = c.target;
    return [t[0] + c.dist * Math.sin(c.yaw) * cp, t[1] + c.dist * Math.sin(c.pitch), t[2] + c.dist * Math.cos(c.yaw) * cp];
  }
  function projector(cam, w, h) {
    const eye = camPos(cam);
    const f = norm(sub(cam.target, eye));
    let r = norm(cross(f, [0, 1, 0]));
    const u = cross(r, f);
    const cx = w / 2, cy = h / 2, focal = 0.5 * h / Math.tan(cam.fov / 2);
    const view = (p) => { const d = sub(p, eye); return [dot(d, r), dot(d, u), dot(d, f)]; };
    const toScreen = (v) => [cx + focal * v[0] / v[2], cy - focal * v[1] / v[2]];
    return {
      eye, f, r, u, focal, view, toScreen,
      point(p) { const v = view(p); return v[2] < NEAR ? null : toScreen(v); },
      polygon(pts) {
        const vs = pts.map(view);
        if (vs.every((v) => v[2] >= NEAR)) return vs.map(toScreen);
        const out = [];
        for (let i = 0; i < vs.length; i++) {
          const a = vs[i], b = vs[(i + 1) % vs.length];
          const ina = a[2] >= NEAR, inb = b[2] >= NEAR;
          if (ina) out.push(a);
          if (ina !== inb) { const t = (NEAR - a[2]) / (b[2] - a[2]); out.push([0, 1, 2].map((k) => a[k] + t * (b[k] - a[k]))); }
        }
        return out.length < 3 ? null : out.map(toScreen);
      },
      ray(x, y) {
        const px = (x - cx) / focal, py = -(y - cy) / focal;
        return [eye, norm([0, 1, 2].map((k) => f[k] + px * r[k] + py * u[k]))];
      },
    };
  }

  // --- Szene aus scene3d -------------------------------------------------------------------
  function zrange(side, depth, fromFace, sc) {
    const half = sc.depth_mm / 2;
    if (side === "front") { const z1 = half - fromFace; return [z1 - depth, z1]; }
    const z0 = -half + fromFace; return [z0, z0 + depth];
  }

  function elide(ctx, txt, w) {
    if (ctx.measureText(txt).width <= w) return txt;
    let s = txt;
    while (s.length > 1 && ctx.measureText(s + "…").width > w) s = s.slice(0, -1);
    return s + "…";
  }

  function labelPainter(lines, fg, big) {
    const name = lines[0] || "", ips = lines.slice(1);
    const font = (size, bold) => `${bold ? "bold " : ""}${Math.max(1, size)}px "Segoe UI", system-ui, Arial, sans-serif`;
    return (ctx, w, h) => {
      ctx.fillStyle = fg;
      ctx.textBaseline = "middle";
      let size = Math.max(6, Math.min(big, h * 0.42));
      if (w < 320) {
        const rows = (name ? [[name, true]] : []).concat(ips.map((ip) => [ip, false]));
        size = Math.max(5, Math.min(size, w / 9, h / (rows.length * 1.25 + 0.4)));
        const n = Math.max(1, Math.min(rows.length, Math.floor(h / (size * 1.25))));
        const top = (h - n * size * 1.25) / 2;
        ctx.textAlign = "center";
        rows.slice(0, n).forEach(([txt, bold], i) => {
          ctx.font = font(bold ? size : size * 0.85, bold);
          ctx.fillText(elide(ctx, txt, w - 16), w / 2, top + (i + 0.5) * size * 1.25);
        });
        return;
      }
      const x0 = 30;
      let nameW = w - 2 * x0;
      if (ips.length) {
        const ipsSize = Math.max(5, Math.min(size * 0.8, h / (ips.length + 0.6)));
        ctx.font = font(ipsSize, false);
        const ipw = Math.min(w * 0.42, Math.max(...ips.map((ip) => ctx.measureText(ip).width)) + 4);
        const rows = Math.min(ips.length, Math.max(1, Math.floor(h / (ipsSize * 1.15))));
        const top = (h - rows * ipsSize * 1.15) / 2;
        ctx.textAlign = "right";
        ips.slice(0, rows).forEach((ip, i) => ctx.fillText(ip, w - 28, top + (i + 0.5) * ipsSize * 1.15));
        nameW = w - ipw - x0 - 44;
      }
      ctx.font = font(size, true);
      ctx.textAlign = "left";
      ctx.fillText(elide(ctx, name, nameW), x0, h / 2);
    };
  }

  function profilePainter(sc, outerLeft, numbers) {
    const width = PROFILE_OUT - PROFILE_IN;
    const holeU = outerLeft ? PROFILE_OUT - HOLE_X : HOLE_X - PROFILE_IN;
    const numW = PROFILE_OUT - EAR_HALF;
    const numX = outerLeft ? 0 : width - numW;
    return (ctx, w, h) => {
      const n = sc.height_u;
      ctx.fillStyle = "rgba(0,0,0,.11)";
      for (let u = 2; u <= n; u += 2) ctx.fillRect(0, h - u * U_MM, w, U_MM);
      const hs = HOLE_SIZE;
      for (let u = 1; u <= n; u++) {
        const base = h - (u - 1) * U_MM;
        for (const off of HOLE_OFFSETS) {
          const cy = base - off;
          ctx.fillStyle = "rgba(255,255,255,.24)";
          ctx.fillRect(holeU - hs / 2 + 0.8, cy - hs / 2 + 0.8, hs, hs);
          ctx.fillStyle = "#16171a";
          ctx.fillRect(holeU - hs / 2, cy - hs / 2, hs, hs);
        }
      }
      ctx.strokeStyle = "#2b2d30"; ctx.lineWidth = 1.6;
      ctx.beginPath();
      for (let u = 0; u <= n; u++) { const y = h - u * U_MM; ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();
      if (numbers) {
        ctx.font = 'bold 14px "Segoe UI", system-ui, Arial, sans-serif';
        ctx.fillStyle = "#141517"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        for (let u = 1; u <= n; u++) ctx.fillText(String(u), numX + numW / 2, h - (u - 0.5) * U_MM);
      }
    };
  }

  function railBoxes(sc, y0, bad) {
    const half = sc.depth_mm / 2, c = bad ? col(RED) : RAIL, out = [];
    for (const sx of [-1, 1]) {
      const [x0, x1] = sx > 0 ? [BODY_HALF, PROFILE_IN] : [-PROFILE_IN, -BODY_HALF];
      out.push(box([x0, y0 + 4, -half + PROFILE_D], [x1, y0 + 16, half - PROFILE_D], c, { outline: [0, 0, 0, 0.31] }));
    }
    return out;
  }

  function shelfDeviceBox(sc, shelf, d, offset, selected, bad, labels) {
    const side = shelf.side;
    const y0 = (shelf.pos - 1) * U_MM;
    const hgt = d.load_u * U_MM;
    const k = BODY_HALF / (sc.shelf_width_mm / 2);
    let x0 = -BODY_HALF + Math.max(0, offset) * k;
    let x1 = Math.min(BODY_HALF, x0 + d.width * k);
    x0 += 0.5; x1 -= 0.5;
    if (side === "rear") [x0, x1] = [-x1, -x0];
    const depth = d.depth > 0 ? d.depth : 150;
    const [z0, z1] = zrange(side, depth, 15, sc);
    let c = col(d.color);
    if (bad) c = mix(c, col(RED), 0.45);
    const sel = d.uid === selected;
    const b = box([x0, y0 + PLATE_H, z0], [x1, y0 + PLATE_H + hgt, z1], c, { uid: d.uid,
      outline: sel ? col(ACCENT) : [0, 0, 0, 0.35], ow: sel ? 2.4 : 0.8 });
    if (labels) {
      const lines = [d.lines[0] || "", ...d.lines.slice(1, 3)];
      if (lines.some(Boolean)) b.decor[side === "front" ? "2,1" : "2,-1"] = labelPainter(lines, d.fg, 14);
    }
    return b;
  }

  function buildBoxes(sc, selected, panels, labels) {
    const boxes = [];
    const H = sc.height_u * U_MM, D = Math.max(sc.depth_mm, 200), half = D / 2, zo = half + CAB_EXTRA;
    const red = col(RED), accent = col(ACCENT);
    boxes.push(box([-OUTER_HALF, -BASE_H, -zo], [OUTER_HALF, 0, zo], FRAME));
    boxes.push(box([-OUTER_HALF + 20, -BASE_H - PLINTH_H, -zo + 20], [OUTER_HALF - 20, -BASE_H, zo - 20], FRAME_DARK));
    boxes.push(box([-OUTER_HALF, H, -zo], [OUTER_HALF, H + TOP_H, zo], FRAME));
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const x0 = sx > 0 ? OUTER_HALF - POST : -OUTER_HALF, z0 = sz > 0 ? zo - POST : -zo;
        boxes.push(box([x0, 0, z0], [x0 + POST, H, z0 + POST], FRAME));
      }
      if (panels) {
        const x0 = sx > 0 ? OUTER_HALF - 3 : -OUTER_HALF;
        boxes.push(box([x0, 0, -zo + POST], [x0 + 3, H, zo - POST], PANEL, { shade: false, outline: [255, 255, 255, 0.1] }));
      }
    }
    for (const [side, zc] of [["front", half], ["rear", -half]]) {
      const [z0, z1] = side === "front" ? [zc - PROFILE_D, zc] : [zc, zc + PROFILE_D];
      for (const sx of [-1, 1]) {
        const [x0, x1] = sx > 0 ? [PROFILE_IN, PROFILE_OUT] : [-PROFILE_OUT, -PROFILE_IN];
        const b = box([x0, 0, z0], [x1, H, z1], PROFILE, { outline: col("#5b5f63") });
        b.decor[side === "front" ? "2,1" : "2,-1"] = profilePainter(sc, (sx < 0) === (side === "front"), labels);
        b.profile = true;
        boxes.push(b);
      }
    }
    for (const it of sc.items) {
      const side = it.side, y0 = (it.pos - 1) * U_MM, span = it.span, bad = it.conflict, sel = it.uid === selected;
      const outward = side === "front" ? "2,1" : "2,-1";
      if (it.shelf) {
        const depth = it.depth || D;
        let c = col(it.color);
        if (bad) c = mix(c, red, 0.55);
        const [z0, z1] = zrange(side, depth, 0, sc);
        boxes.push(box([-BODY_HALF, y0, z0], [BODY_HALF, y0 + PLATE_H, z1], c, { uid: it.uid,
          outline: sel ? accent : bad ? red : null, ow: sel || bad ? 2.2 : 0.8 }));
        const [ez0, ez1] = zrange(side, EAR_D, -EAR_D, sc);
        for (const sx of [-1, 1]) {
          const [x0, x1] = sx > 0 ? [BODY_HALF, EAR_HALF] : [-EAR_HALF, -BODY_HALF];
          boxes.push(box([x0, y0, ez0], [x1, y0 + U_MM * it.height_u - 1, ez1], c, { uid: it.uid,
            outline: sel ? accent : null, ow: sel ? 2.2 : 0.8 }));
        }
        if (it.rails) boxes.push(...railBoxes(sc, y0, bad));
        for (const d of it.devices) boxes.push(shelfDeviceBox(sc, it, d, d.offset, selected, bad, labels));
        continue;
      }
      let c = col(it.color);
      if (bad) c = mix(c, red, 0.55);
      const depth = it.depth > 0 ? it.depth : UNKNOWN_DEPTH;
      const top = y0 + span * U_MM - 0.8, bottom = y0 + 0.8;
      const outline = sel ? accent : bad ? red : [0, 0, 0, 0.35];
      const ow = sel || bad ? 2.4 : 0.8;
      const lines = labels ? [it.lines[0] || "", ...it.lines.slice(1)] : [];
      if (it.rackmount) {
        const [z0, z1] = zrange(side, Math.max(depth - EAR_D, 1), 0, sc);
        boxes.push(box([-BODY_HALF, bottom, z0], [BODY_HALF, top, z1], shade(c, 0.82), { uid: it.uid, outline, ow }));
        const [ez0, ez1] = zrange(side, EAR_D, -EAR_D, sc);
        const front = box([-EAR_HALF, bottom, ez0], [EAR_HALF, top, ez1], c, { uid: it.uid, outline, ow });
        if (lines.some(Boolean)) front.decor[outward] = labelPainter(lines, it.fg, 22);
        boxes.push(front);
        if (it.rails) boxes.push(...railBoxes(sc, y0, bad));
      } else {
        const hh = it.height_cm > 0 ? it.height_cm * 10 : span * U_MM;
        const w = Math.min(it.width || 440, 2 * BODY_HALF) / 2;
        const [z0, z1] = zrange(side, depth, 0, sc);
        const b = box([-w, bottom, z0], [w, Math.min(top, y0 + hh), z1], c, { uid: it.uid, outline, ow });
        if (lines.some(Boolean)) b.decor[outward] = labelPainter(lines, it.fg, 18);
        boxes.push(b);
      }
    }
    return boxes;
  }

  // --- Zeichnen --------------------------------------------------------------------------
  function separates(a, b, eye) {
    for (let k = 0; k < 3; k++) {
      if (a.hi[k] <= b.lo[k] + EPS) { if (eye[k] >= b.lo[k]) return -1; if (eye[k] <= a.hi[k]) return 1; return 0; }
      if (b.hi[k] <= a.lo[k] + EPS) { if (eye[k] >= a.lo[k]) return 1; if (eye[k] <= b.hi[k]) return -1; return 0; }
    }
    return 2;
  }
  function hull(points) {
    const pts = points.map((p) => [Math.round(p[0] * 1000) / 1000, Math.round(p[1] * 1000) / 1000])
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (pts.length < 3) return pts;
    const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [], upper = [];
    for (const q of pts) { while (lower.length >= 2 && cr(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
    for (let i = pts.length - 1; i >= 0; i--) { const q = pts[i]; while (upper.length >= 2 && cr(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
  }
  function convexOverlap(a, b) {
    // Trennachsen-Test zweier konvexer Polygone (echte Überdeckung, nicht nur Berührung)
    for (const poly of [a, b]) {
      for (let i = 0; i < poly.length; i++) {
        const p = poly[i], q = poly[(i + 1) % poly.length];
        const nx = q[1] - p[1], ny = p[0] - q[0];
        let amin = Infinity, amax = -Infinity, bmin = Infinity, bmax = -Infinity;
        for (const v of a) { const d = v[0] * nx + v[1] * ny; amin = Math.min(amin, d); amax = Math.max(amax, d); }
        for (const v of b) { const d = v[0] * nx + v[1] * ny; bmin = Math.min(bmin, d); bmax = Math.max(bmax, d); }
        const tol = 1e-6 * (Math.abs(nx) + Math.abs(ny));
        if (amax <= bmin + tol || bmax <= amin + tol) return false;
      }
    }
    return true;
  }
  function overlaps(a, b) {
    const r = a.rect, s = b.rect;
    if (r[2] <= s[0] || s[2] <= r[0] || r[3] <= s[1] || s[3] <= r[1]) return false;
    if (a.hull.length < 3 || b.hull.length < 3) return false;
    return convexOverlap(a.hull, b.hull);
  }
  function sortBoxes(boxes, eye) {
    const n = boxes.length, after = boxes.map(() => []), indeg = new Array(n).fill(0);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      if (!overlaps(boxes[i], boxes[j])) continue;
      let s = separates(boxes[i], boxes[j], eye);
      if (s === 2) s = boxes[i].dist > boxes[j].dist ? -1 : 1;
      if (s === -1) { after[i].push(j); indeg[j]++; } else if (s === 1) { after[j].push(i); indeg[i]++; }
    }
    const done = new Array(n).fill(false), out = [];
    let ready = [];
    for (let i = 0; i < n; i++) if (!indeg[i]) ready.push(i);
    while (out.length < n) {
      if (!ready.length) {     // Zyklus: den entferntesten verbleibenden Quader nehmen
        let best = -1;
        for (let k = 0; k < n; k++) if (!done[k] && (best < 0 || boxes[k].dist > boxes[best].dist)) best = k;
        ready.push(best);
      }
      let bi = 0;
      for (let k = 1; k < ready.length; k++) if (boxes[ready[k]].dist > boxes[ready[bi]].dist) bi = k;
      const i = ready.splice(bi, 1)[0];
      if (done[i]) continue;
      done[i] = true; out.push(boxes[i]);
      for (const j of after[i]) if (--indeg[j] === 0 && !done[j]) ready.push(j);
    }
    return out;
  }

  function facePolys(proj, b) {
    const eye = proj.eye;
    b.polys = [];
    for (const [axis, sign] of FACES) {
      if (sign > 0 && eye[axis] <= b.hi[axis]) continue;
      if (sign < 0 && eye[axis] >= b.lo[axis]) continue;
      const poly = proj.polygon(faceCorners(b.lo, b.hi, axis, sign));
      if (poly) b.polys.push([axis, sign, poly]);
    }
  }

  function pathPoly(ctx, poly) {
    ctx.beginPath();
    ctx.moveTo(poly[0][0], poly[0][1]);
    for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i][0], poly[i][1]);
    ctx.closePath();
  }

  function drawDecor(ctx, proj, b, axis, sign, fn) {
    const pts = faceCorners(b.lo, b.hi, axis, sign).map((c) => proj.point(c));
    if (pts.some((p) => !p)) return;
    const [w, h] = faceSize(b.lo, b.hi, axis);
    const ys = pts.map((p) => p[1]);
    if (Math.max(...ys) - Math.min(...ys) < 5) return;          // zu klein, um lesbar zu sein
    const [p0, p1, , p3] = pts;
    ctx.save();
    ctx.transform((p1[0] - p0[0]) / w, (p1[1] - p0[1]) / w, (p3[0] - p0[0]) / h, (p3[1] - p0[1]) / h, p0[0], p0[1]);
    ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.clip();
    fn(ctx, w, h);
    ctx.restore();
  }

  function drawBox(ctx, proj, b, light, decor) {
    for (const [axis, sign, poly] of b.polys) {
      const n = [0, 0, 0]; n[axis] = sign;
      let c = b.color;
      if (b.shade) c = shade(c, 0.42 + 0.68 * Math.max(0, dot(n, light)));
      pathPoly(ctx, poly);
      ctx.fillStyle = css(c);
      ctx.fill();
      ctx.lineJoin = "round";
      ctx.lineWidth = b.outline ? b.ow : 0.6;
      ctx.strokeStyle = css(b.outline || shade(c, 0.7));
      ctx.stroke();
      const fn = decor ? b.decor[`${axis},${sign}`] : null;
      if (fn) drawDecor(ctx, proj, b, axis, sign, fn);
    }
  }

  function clipSegment(proj, a, b) {
    let va = proj.view(a), vb = proj.view(b);
    if (va[2] < NEAR && vb[2] < NEAR) return null;
    if (va[2] < NEAR || vb[2] < NEAR) {
      const t = (NEAR - va[2]) / (vb[2] - va[2]);
      const c = [0, 1, 2].map((k) => va[k] + t * (vb[k] - va[k]));
      if (va[2] < NEAR) va = c; else vb = c;
    }
    return [proj.toScreen(va), proj.toScreen(vb)];
  }

  function drawFloor(ctx, proj, y, texts, textZ) {
    ctx.strokeStyle = "rgba(255,255,255,.07)"; ctx.lineWidth = 1;
    ctx.beginPath();
    const ext = 2400, step = 200;
    for (let k = -ext; k <= ext; k += step) {
      for (const [a, b] of [[[k, y, -ext], [k, y, ext]], [[-ext, y, k], [ext, y, k]]]) {
        const seg = clipSegment(proj, a, b);
        if (seg) { ctx.moveTo(seg[0][0], seg[0][1]); ctx.lineTo(seg[1][0], seg[1][1]); }
      }
    }
    ctx.stroke();
    texts.forEach((txt, i) => {
      if (!txt) return;
      const rot = i === 1, z = (rot ? -1 : 1) * textZ;
      const quad = !rot ? [[-500, y, z], [500, y, z], [500, y, z + 160], [-500, y, z + 160]]
        : [[500, y, z], [-500, y, z], [-500, y, z - 160], [500, y, z - 160]];
      const pts = quad.map((c) => proj.point(c));
      if (pts.some((p) => !p)) return;
      const [p0, p1, , p3] = pts;
      ctx.save();
      ctx.transform((p1[0] - p0[0]) / 1000, (p1[1] - p0[1]) / 1000, (p3[0] - p0[0]) / 160, (p3[1] - p0[1]) / 160, p0[0], p0[1]);
      ctx.font = 'bold 90px "Segoe UI", system-ui, Arial, sans-serif';
      if ("letterSpacing" in ctx) ctx.letterSpacing = "14px";
      ctx.fillStyle = "rgba(255,255,255,.16)"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(txt, 500, 80);
      ctx.restore();
    });
  }

  function render(ctx, cam, boxes, w, h, { floorY = -BASE_H - PLINTH_H, ghost = null, background = true,
                                         floorTexts = ["", ""], textZ = 700, fast = false } = {}) {
    const proj = projector(cam, w, h), eye = proj.eye;
    if (background) {
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#3a3c3f"); g.addColorStop(1, "#1c1d1f");
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    }
    drawFloor(ctx, proj, floorY, fast ? ["", ""] : floorTexts, textZ);
    let light = norm([0, 1, 2].map((k) => -proj.f[k] * 0.7 - proj.r[k] * 0.35));
    light = norm([light[0], light[1] + 0.9, light[2]]);
    const visible = [];
    for (const b of boxes) {
      facePolys(proj, b);
      if (!b.polys.length) continue;
      const all = b.polys.flatMap((p) => p[2]);
      const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
      b.rect = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      b.hull = hull(all);
      b.dist = dist3(center(b), eye);
      visible.push(b);
    }
    const ordered = sortBoxes(visible, eye);
    for (const b of ordered) drawBox(ctx, proj, b, light, !fast);
    if (ghost) { facePolys(proj, ghost); drawBox(ctx, proj, ghost, light, false); }
    return ordered;
  }

  function pointInPoly(x, y, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  // --- Ansicht -----------------------------------------------------------------------------
  /**
   * container: Element, in das die Ansicht gesetzt wird.
   * cb: { select(uid), move(uid, pos), shelfMove(uid, shelfUid, offset), side(side), fine() }
   */
  function create(container, cb) {
    const canvas = document.createElement("canvas");
    canvas.className = "v3d-canvas";
    canvas.tabIndex = 0;
    const bar = document.createElement("div");
    bar.className = "v3d-bar";
    container.append(canvas, bar);
    const ctx = canvas.getContext("2d");

    const st = {
      view: null, sc: null, selected: "", readOnly: false, panels: true, labels: true,
      cam: camera(), boxes: [], drawn: [], ghost: null, press: null, drag: null,
      anim: null, fast: false, settle: 0, side: null, w: 1, h: 1, fitted: false, dirty: true,
    };

    const buttons = {};
    const addBtn = (key, text, tip, fn, toggle) => {
      const b = document.createElement("button");
      b.textContent = text; b.title = tip; b.type = "button";
      if (toggle) b.classList.add("toggle", "on");
      b.addEventListener("click", () => { fn(b); canvas.focus(); });
      bar.append(b); buttons[key] = b;
    };
    for (const [key, text, tip] of [["front", "Vorne", "Ansicht von vorne"], ["rear", "Hinten", "Ansicht von hinten"],
      ["left", "Links", "Ansicht von links"], ["right", "Rechts", "Ansicht von rechts"], ["top", "Oben", "Ansicht von schräg oben"],
      ["iso", "3D", "Schräge 3D-Ansicht"]]) addBtn(key, text, tip, () => preset(key));
    addBtn("fit", "Anpassen", "Ganzen Schrank zeigen (Strg + 0)", () => fit());
    bar.append(Object.assign(document.createElement("span"), { className: "gap" }));
    addBtn("panels", "Seitenwände", "Seitenwände ein-/ausblenden", (b) => { st.panels = !st.panels; b.classList.toggle("on", st.panels); rebuild(); }, true);
    addBtn("labels", "Beschriftung", "Namen, IP-Adressen und HE-Nummern ein-/ausblenden", (b) => { st.labels = !st.labels; b.classList.toggle("on", st.labels); rebuild(); }, true);

    function rebuild() {
      st.boxes = st.sc ? buildBoxes(st.sc, st.readOnly ? "" : st.selected, st.panels, st.labels) : [];
      draw();
    }
    function bounds() {
      const H = (st.sc?.height_u || 12) * U_MM, zo = Math.max(st.sc?.depth_mm || 800, 200) / 2 + CAB_EXTRA;
      return [[-OUTER_HALF, -BASE_H - PLINTH_H, -zo], [OUTER_HALF, H + TOP_H, zo]];
    }
    function fitCam(cam) {
      const [lo, hi] = bounds();
      cam.target = [0, 1, 2].map((k) => (lo[k] + hi[k]) / 2);
      const r = 0.5 * dist3(lo, hi);
      const hv = cam.fov / 2, hh = Math.atan(Math.tan(hv) * st.w / st.h);
      cam.dist = r / Math.sin(Math.min(hv, hh)) * 0.98;
    }
    function go(target, animate = true) {
      const dy = ((target.yaw - st.cam.yaw + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
      target.yaw = st.cam.yaw + dy;
      if (!animate || !container.offsetParent) { st.anim = null; st.cam = target; camChanged(false); return; }
      st.anim = { from: copyCam(st.cam), to: target, t: 0 };
      requestAnimationFrame(step);
    }
    function step() {
      const a = st.anim;
      if (!a) return;
      a.t = Math.min(1, a.t + 0.08);
      const e = a.t * a.t * (3 - 2 * a.t);
      const c = copyCam(a.to);
      c.yaw = a.from.yaw + (a.to.yaw - a.from.yaw) * e;
      c.pitch = a.from.pitch + (a.to.pitch - a.from.pitch) * e;
      c.dist = a.from.dist + (a.to.dist - a.from.dist) * e;
      c.target = [0, 1, 2].map((k) => a.from.target[k] + (a.to.target[k] - a.from.target[k]) * e);
      st.cam = c;
      if (a.t >= 1) st.anim = null; else requestAnimationFrame(step);
      camChanged(true);
    }
    function fit(animate = true) { const t = copyCam(st.cam); fitCam(t); go(t, animate); }
    function preset(key, animate = true) {
      const [yaw, pitch] = PRESETS[key];
      const t = copyCam(st.cam); t.yaw = rad(yaw); t.pitch = rad(pitch); fitCam(t); go(t, animate);
    }
    const facing = () => (Math.cos(st.cam.yaw) >= 0 ? "front" : "rear");
    function showSide(side, animate = true) { if (facing() !== side) preset(side === "front" ? "front" : "rear", animate); }
    function zoom(f) { st.cam.dist = Math.min(20000, Math.max(150, st.cam.dist / f)); camChanged(true); }
    function camChanged(interactive) {
      if (interactive) {
        st.fast = true;
        clearTimeout(st.settle);
        st.settle = setTimeout(function settle() {
          if (st.press || st.anim) { st.settle = setTimeout(settle, 160); return; }
          st.fast = false; draw();
        }, 160);
      }
      const old = st.side;
      st.side = facing();
      if (old !== null && old !== st.side && cb.side) cb.side(st.side);
      draw();
    }
    function focusItem(uid) {
      const b = st.boxes.find((x) => x.uid === uid);
      const it = topOf(uid);
      if (!b || !it) return;
      const t = copyCam(st.cam);
      t.target = center(b);
      t.yaw = (it.side === "front" ? 0 : Math.PI) + rad(it.side === "front" ? -25 : 25);
      t.pitch = rad(14); t.dist = 1300;
      go(t, true);
    }

    let raf = 0;
    function draw() {
      if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; paint(); });
    }
    function resize() {
      const r = container.getBoundingClientRect();
      const w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
      if (w === st.w && h === st.h && canvas.width) return false;
      st.w = w; st.h = h;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
      return true;
    }
    function paint() {
      if (!container.offsetParent) return;
      const changed = resize();
      if (!st.fitted && st.sc) { st.fitted = true; const t = copyCam(st.cam); fitCam(t); st.cam = t; st.side = facing(); }
      else if (changed && !st.anim && !st.press) { /* Größe geändert: Kamera bleibt */ }
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      st.drawn = render(ctx, st.cam, st.boxes, st.w, st.h, { ghost: st.ghost, floorTexts: ["VORNE", "HINTEN"],
        textZ: bounds()[1][2] + 60, fast: st.fast });
      overlay();
    }
    function overlay() {
      if (!st.sc) return;
      const x = 14, y = bar.offsetTop + bar.offsetHeight + 22;
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.font = 'bold 15px "Segoe UI", system-ui, Arial, sans-serif'; ctx.fillStyle = TEXT;
      ctx.fillText(st.sc.name, x, y);
      ctx.font = '12px "Segoe UI", system-ui, Arial, sans-serif'; ctx.fillStyle = MUTED;
      const [yy, mm, dd] = (st.sc.as_of || "").split("-");
      ctx.fillText(`Stand ${dd}.${mm}.${yy} · ${st.sc.height_u} HE · Tiefe ${st.sc.depth_mm} mm · Blick von ${facing() === "front" ? "vorne" : "hinten"}`, x, y + 18);
      if (st.readOnly) { ctx.fillStyle = ACCENT; ctx.fillText("Früherer Stand – nur ansehen", x, y + 36); }
      const hint = st.readOnly ? "Linke/rechte Maustaste: drehen · Mittlere Maustaste / Umschalt: verschieben · Mausrad: zoomen"
        : "Linke Maustaste: drehen · auf einem Gerät: verschieben (auch auf andere Fachböden) · Mittlere Maustaste / Umschalt: Ansicht verschieben · Mausrad: zoomen · Doppelklick: Gerät heranholen";
      ctx.fillStyle = "rgba(255,255,255,.43)";
      ctx.fillText(elide(ctx, hint, st.w - 20), 10, st.h - 12);
      if (st.drag && st.drag.text) {
        ctx.font = 'bold 12px "Segoe UI", system-ui, Arial, sans-serif'; ctx.fillStyle = TEXT;
        ctx.fillText(st.drag.text, st.drag.mouse[0] + 16, st.drag.mouse[1] - 10);
      }
    }

    // --- Daten ---------------------------------------------------------------------------
    function topOf(uid) {
      if (!st.sc) return null;
      for (const it of st.sc.items) {
        if (it.uid === uid) return it;
        if (it.devices && it.devices.some((d) => d.uid === uid)) return it;
      }
      return null;
    }
    function devOf(uid) {
      for (const it of st.sc?.items || []) for (const d of it.devices || []) if (d.uid === uid) return [d, it];
      return [null, null];
    }
    function update(view, { readOnly = false } = {}) {
      st.view = view; st.sc = view.scene3d; st.selected = view.selected || ""; st.readOnly = readOnly;
      rebuild();
    }

    // --- Maus ----------------------------------------------------------------------------
    function pick(x, y) {
      for (let i = st.drawn.length - 1; i >= 0; i--) {
        const b = st.drawn[i];
        if (!b.uid) continue;
        for (const p of b.polys) if (pointInPoly(x, y, p[2])) return b.uid;
      }
      return "";
    }
    function planePoint(x, y, c) {
      const proj = projector(st.cam, st.w, st.h);
      let n = [proj.f[0], 0, proj.f[2]];
      if (Math.hypot(n[0], n[2]) < 0.15) return null;
      n = norm(n);
      const [o, d] = proj.ray(x, y);
      const den = dot(d, n);
      if (Math.abs(den) < 1e-6) return null;
      const t = dot(sub(c, o), n) / den;
      if (t <= 0) return null;
      return [0, 1, 2].map((k) => o[k] + d[k] * t);
    }
    function startDrag(uid, x, y) {
      const top = topOf(uid), b = st.boxes.find((q) => q.uid === uid), t = st.view?.targets;
      if (!top || !b || !t) return null;
      const c = center(b), p = planePoint(x, y, c);
      if (!p) return null;
      const [dev] = devOf(uid);
      if (dev) return { shelfMode: true, uid, dev, grabX: p[0] - b.lo[0], grabY: p[1] - b.lo[1], center: c,
                        active: false, target: null, ok: false, mouse: [x, y], text: "", info: t.devs[uid] };
      return { uid, top, grab: p[1] / U_MM - (top.pos - 1), center: c, active: false, pos: top.pos, ok: true,
               mouse: [x, y], text: "", info: t.tops[top.uid] };
    }
    function updateDrag(x, y) {
      const d = st.drag;
      d.mouse = [x, y];
      if (d.shelfMode) return updateShelfDrag(x, y);
      const p = planePoint(x, y, d.center);
      if (!p || !d.info) return;
      const span = d.top.span, H = st.sc.height_u;
      const raw = p[1] / U_MM - d.grab + 1;
      let pos = (cb.fine && cb.fine()) || Math.abs(span - Math.round(span)) > EPS ? Math.round(raw * 3) / 3 : Math.round(raw);
      pos = Math.max(1, Math.min(H - span + 1, pos));
      const same = Math.abs(pos - d.top.pos) < EPS;
      const ok = same || d.info.ok.includes(Math.round(pos * 3));
      d.pos = pos; d.ok = ok;
      d.text = `HE ${fmtU(pos)}` + (ok ? "" : " – belegt");
      const y0 = (pos - 1) * U_MM;
      const depth = Math.max(UNKNOWN_DEPTH, d.top.shelf ? (d.top.depth || st.sc.depth_mm) : (d.top.depth || 0));
      const [z0, z1] = zrange(d.top.side, depth, -EAR_D, st.sc);
      st.ghost = box([-EAR_HALF - 2, y0, z0 - 1], [EAR_HALF + 2, y0 + span * U_MM, z1 + 1], ok ? GHOST_OK : GHOST_BAD,
                     { outline: [255, 255, 255, 0.63], ow: 1.5, shade: false });
      canvas.style.cursor = "ns-resize";
      draw();
    }
    function updateShelfDrag(x, y) {
      const d = st.drag, dev = d.dev;
      const p = planePoint(x, y, d.center);
      if (!p || !d.info) return;
      const xLeft = p[0] - d.grabX, yBottom = p[1] - d.grabY;
      const devH = dev.load_u * U_MM, face = facing();
      let best = null;
      for (const s of st.sc.items) {
        if (!s.shelf || !(s.uid in d.info.targets)) continue;
        const dist = Math.abs(yBottom - ((s.pos - 1) * U_MM + PLATE_H));
        if (dist > Math.max(devH, U_MM)) continue;
        const key = [s.side !== face ? 1 : 0, dist];
        if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1])) best = { key, s };
      }
      const swm = st.sc.shelf_width_mm, k = BODY_HALF / (swm / 2);
      let lo, hi;
      if (!best) {
        d.target = null; d.ok = false; d.text = "Auf einen Fachboden ziehen";
        lo = [xLeft, yBottom, d.center[2] - 20];
        hi = [xLeft + dev.width * k, yBottom + devH, d.center[2] + 20];
      } else {
        const s = best.s;
        let off = s.side === "rear" ? (-xLeft - dev.width * k + BODY_HALF) / k : (xLeft + BODY_HALF) / k;
        off = Math.max(0, Math.min(Math.round(off / 5) * 5, swm - dev.width));
        const ok = d.info.targets[s.uid].includes(off) || (dev.offset === off && devOf(dev.uid)[1]?.uid === s.uid);
        d.target = { shelf: s.uid, offset: off }; d.ok = ok;
        d.text = `Fachboden HE ${fmtU(s.pos)} · ${off} mm von links` + (ok ? "" : " – kein Platz");
        const b = shelfDeviceBox(st.sc, s, dev, off, "", false, false);
        lo = b.lo; hi = b.hi;
      }
      st.ghost = box([lo[0] - 1, lo[1], lo[2] - 1], [hi[0] + 1, hi[1] + 1, hi[2] + 1], d.ok ? GHOST_OK : GHOST_BAD,
                     { outline: [255, 255, 255, 0.63], ow: 1.5, shade: false });
      canvas.style.cursor = "grabbing";
      draw();
    }
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };

    canvas.addEventListener("pointerdown", (e) => {
      canvas.focus();
      st.anim = null;
      const [x, y] = pos(e);
      st.press = { x, y, button: e.button, shift: e.shiftKey, cam: copyCam(st.cam), uid: null };
      st.drag = null;
      if (e.button === 0 && !e.shiftKey) {
        const uid = pick(x, y);
        if (uid && !st.readOnly) st.drag = startDrag(uid, x, y);
        st.press.uid = uid;
      }
      canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    canvas.addEventListener("pointermove", (e) => {
      const [x, y] = pos(e);
      if (!st.press) {
        const uid = pick(x, y);
        canvas.style.cursor = uid && !st.readOnly ? "pointer" : "default";
        return;
      }
      const dx = x - st.press.x, dy = y - st.press.y;
      if (st.drag) {
        if (!st.drag.active && Math.hypot(dx, dy) < 4) return;
        st.drag.active = true;
        updateDrag(x, y);
        return;
      }
      if (Math.hypot(dx, dy) < 2) return;
      const c0 = st.press.cam;
      if (st.press.button === 1 || st.press.shift) {
        const proj = projector(c0, st.w, st.h), s = c0.dist / proj.focal;
        st.cam.target = [0, 1, 2].map((k) => c0.target[k] - (dx * proj.r[k] - dy * proj.u[k]) * s);
      } else {
        st.cam.yaw = c0.yaw - dx * 0.008;
        st.cam.pitch = Math.max(rad(-80), Math.min(rad(85), c0.pitch + dy * 0.008));
      }
      canvas.style.cursor = "grabbing";
      camChanged(true);
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!st.press) return;
      const [x, y] = pos(e);
      const moved = Math.hypot(x - st.press.x, y - st.press.y) >= 4;
      const d = st.drag;
      st.press = null; st.drag = null; st.ghost = null;
      canvas.style.cursor = "default";
      if (d && d.active) {
        if (d.shelfMode) {
          const [dev, shelf] = devOf(d.uid);
          if (d.ok && d.target && dev && (shelf?.uid !== d.target.shelf || dev.offset !== d.target.offset))
            cb.shelfMove(d.uid, d.target.shelf, d.target.offset);
        } else if (d.ok && Math.abs(d.pos - d.top.pos) > EPS) cb.move(d.top.uid, d.pos);
        draw();
        return;
      }
      if (!moved && e.button === 0) {
        const uid = pick(x, y);
        if (uid !== st.selected) { st.selected = uid; rebuild(); cb.select(uid); }
      }
      draw();
    });
    canvas.addEventListener("dblclick", (e) => { const [x, y] = pos(e); const uid = pick(x, y); if (uid) focusItem(uid); });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const steps = -e.deltaY / (e.deltaMode === 1 ? 3 : 100);
      if (steps) zoom(Math.pow(1.15, Math.max(-3, Math.min(3, steps))));
    }, { passive: false });
    canvas.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") st.cam.yaw -= rad(10);
      else if (e.key === "ArrowRight") st.cam.yaw += rad(10);
      else if (e.key === "+" || e.key === "=") { zoom(1.15); return; }
      else if (e.key === "-") { zoom(1 / 1.15); return; }
      else return;
      e.preventDefault();
      camChanged(true);
    });
    new ResizeObserver(() => draw()).observe(container);

    /** PNG der aktuellen Ansicht mit Titel und Stand (doppelte Auflösung). */
    function toPng(title, subtitle, scale = 2) {
      const w = Math.max(800, st.w), h = Math.max(600, st.h);
      const c = document.createElement("canvas");
      c.width = w * scale; c.height = h * scale;
      const g = c.getContext("2d");
      g.scale(scale, scale);
      const cam = copyCam(st.cam);
      render(g, cam, buildBoxes(st.sc, "", st.panels, true), w, h, { floorTexts: ["", ""] });
      g.textAlign = "left"; g.textBaseline = "middle";
      g.font = 'bold 22px "Segoe UI", system-ui, Arial, sans-serif'; g.fillStyle = TEXT;
      g.fillText(title, 20, 29);
      g.font = '14px "Segoe UI", system-ui, Arial, sans-serif'; g.fillStyle = MUTED;
      g.fillText(subtitle, 20, 55);
      return new Promise((res) => c.toBlob(res, "image/png"));
    }

    return {
      update, fit, preset, zoom, showSide, facing, focusItem, toPng, draw,
      focus: () => canvas.focus(),
      get camera() { return st.cam; },
      _state: st, _pick: pick,
    };
  }

  function fmtU(v) {
    const whole = Math.floor(v + 1e-9), frac = Math.round((v - whole) * 3);
    return frac === 0 ? String(whole) : `${whole}${frac === 1 ? "⅓" : "⅔"}`;
  }

  return { create, buildBoxes, render, camera, projector, U_MM, PLATE_H };
})();
