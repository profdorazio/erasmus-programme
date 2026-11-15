#!/usr/bin/env python3
"""Genera src/europe.json: i confini dei paesi europei, già proiettati e semplificati,
usati da build.py per disegnare la mappa interattiva della home.

Va lanciato solo se si vuole cambiare l'inquadratura della mappa (FRAME) o il dettaglio.

Uso:
  curl -L -o /tmp/countries-50m.json https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json
  python3 tools/make_map.py /tmp/countries-50m.json

Dati: Natural Earth (dominio pubblico) via world-atlas.
Proiezione: azimutale equivalente di Lambert centrata sull'Europa (come EPSG:3035).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "europe.json"

LON0, LAT0 = 10.0, 50.0          # centro della proiezione
WIDTH = 1000.0                    # larghezza del viewBox SVG
TOLERANCE = 0.55                  # semplificazione Douglas-Peucker (unità viewBox)
MIN_AREA = 2.0                    # scarta isolette più piccole di così (unità²)
# Punti (lon, lat) che l'inquadratura deve contenere: Madeira a sud-ovest, Grecia/Turchia a est.
FRAME = [(-19.5, 31.5), (-12, 59), (10, 63.5), (34, 58), (31, 34.5), (10, 32)]


def laea(lon: float, lat: float) -> tuple[float, float]:
    l, p = math.radians(lon - LON0), math.radians(lat)
    p0 = math.radians(LAT0)
    k = math.sqrt(2 / (1 + math.sin(p0) * math.sin(p) + math.cos(p0) * math.cos(p) * math.cos(l)))
    x = k * math.cos(p) * math.sin(l)
    y = k * (math.cos(p0) * math.sin(p) - math.sin(p0) * math.cos(p) * math.cos(l))
    return x, -y  # y verso il basso, come in SVG


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring_coords(ring: list[int], arcs) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for idx in ring:
        a = arcs[idx] if idx >= 0 else arcs[~idx][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def clip(poly, xmin, ymin, xmax, ymax):
    """Sutherland–Hodgman su rettangolo."""
    def edge(pts, inside, inter):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out

    def ix(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))

    def iy(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), y)

    for inside, inter in (
        (lambda p: p[0] >= xmin, lambda a, b: ix(a, b, xmin)),
        (lambda p: p[0] <= xmax, lambda a, b: ix(a, b, xmax)),
        (lambda p: p[1] >= ymin, lambda a, b: iy(a, b, ymin)),
        (lambda p: p[1] <= ymax, lambda a, b: iy(a, b, ymax)),
    ):
        if not poly:
            break
        poly = edge(poly, inside, inter)
    return poly


def dp(pts, tol):
    """Douglas-Peucker iterativo."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        best, bi = 0.0, -1
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            dist = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if dist > best:
                best, bi = dist, i
        if best > tol and bi > 0:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def area(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def main(src: str) -> None:
    topo = json.loads(Path(src).read_text())
    arcs = decode_arcs(topo)

    fx = [laea(*p) for p in FRAME]
    xmin, xmax = min(p[0] for p in fx), max(p[0] for p in fx)
    ymin, ymax = min(p[1] for p in fx), max(p[1] for p in fx)
    scale = WIDTH / (xmax - xmin)
    height = round((ymax - ymin) * scale, 1)

    def to_view(lon, lat):
        x, y = laea(lon, lat)
        return ((x - xmin) * scale, (y - ymin) * scale)

    countries = {}
    pad = 5
    for g in topo["objects"]["countries"]["geometries"]:
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        parts = []
        for poly in polys:
            for ring in poly:
                coords = ring_coords(ring, arcs)
                # scarta anelli lontanissimi (es. Siberia, Americhe) prima di proiettare
                if all(not (-40 < lon < 70 and 20 < lat < 80) for lon, lat in coords):
                    continue
                pts = [to_view(lon, lat) for lon, lat in coords]
                pts = clip(pts, -pad, -pad, WIDTH + pad, height + pad)
                if len(pts) < 3 or area(pts) < MIN_AREA:
                    continue
                # anello chiuso: lo spezzo nel punto più lontano dall'inizio e semplifico le due metà
                far = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
                pts = dp(pts[:far + 1], TOLERANCE)[:-1] + dp(pts[far:] + [pts[0]], TOLERANCE)[:-1]
                if len(pts) < 3:
                    continue
                parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        if parts:
            countries[g.get("id") or g["properties"]["name"]] = {"name": g["properties"]["name"], "d": "".join(parts)}

    data = {
        "source": "Natural Earth 1:50m via world-atlas@2.0.2",
        "projection": {"lon0": LON0, "lat0": LAT0, "xmin": xmin, "ymin": ymin, "scale": scale},
        "width": WIDTH,
        "height": height,
        "countries": countries,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = sum(len(c["d"]) for c in countries.values())
    print(f"{OUT.relative_to(ROOT)}: {len(countries)} paesi, viewBox {WIDTH:.0f}×{height}, path {size/1024:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
