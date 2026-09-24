# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Proposals for green/yellow cable sections; calibration remains explicit.

Detection uses pixel geometry only, never nominal dimensions to force a fit.
Every proposal must be reviewed before it becomes a measurement.
"""
from functools import lru_cache

import cv2
import numpy as np


class DetectionError(ValueError):
    pass


def circle_fit(points):
    points = np.asarray(points, dtype=float)
    x, y = points.T
    a, b, c = np.linalg.lstsq(
        np.column_stack((2*x, 2*y, np.ones(len(x)))), x*x+y*y, rcond=None
    )[0]
    radius = np.sqrt(max(0, c+a*a+b*b))
    center = np.array([a, b])
    errors = np.abs(np.linalg.norm(points-center, axis=1)-radius)
    return center, radius, errors


def sample(image, points):
    points = np.asarray(points)
    return cv2.remap(image, points[..., 0].astype(np.float32),
                     points[..., 1].astype(np.float32), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT)


def color_mask(hsv, low, high, kernel_size):
    mask = cv2.inRange(hsv, np.array(low), np.array(high))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(mask)
    for contour in contours:
        if cv2.contourArea(contour) > mask.size * .003:
            cv2.drawContours(filled, [contour], -1, 255, -1)
    return mask, filled


def outer_circles(mask, count):
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    yy, xx = np.indices(mask.shape)
    lobes = []
    angles = np.linspace(0, 2*np.pi, 180, endpoint=False)
    directions = np.column_stack((np.cos(angles), np.sin(angles)))
    for _ in range(count):
        _, seed_radius, _, seed = cv2.minMaxLoc(distance)
        if seed_radius < min(mask.shape) * .022:
            raise DetectionError("Not enough distinct colored lobes. Use manual measurement or crop the image.")
        center = np.array(seed, dtype=float)
        radii = np.arange(seed_radius*.5, seed_radius*1.65, .75)
        rays = center + directions[:, None, :] * radii[None, :, None]
        values = sample(mask, rays)
        outside = values < 128
        valid = np.any(outside, axis=1)
        indices = np.argmax(outside, axis=1)
        points = rays[np.arange(len(angles)), indices][valid]
        # Exclude the bridge and arcs that run into an adjacent lobe.
        lengths = np.linalg.norm(points-center, axis=1)
        points = points[lengths < np.median(lengths)*1.18]
        for _ in range(3):
            fitted_center, radius, errors = circle_fit(points)
            keep = errors < max(2.5, np.median(errors)*2.8)
            if keep.all() or keep.sum() < 40:
                break
            points = points[keep]
        fitted_center, radius, errors = circle_fit(points)
        if len(points) < 40 or not .7*seed_radius < radius < 1.5*seed_radius:
            raise DetectionError("An outer contour is ambiguous. Use manual measurement.")
        lobes.append(dict(center=fitted_center, radius=radius, outer=points,
                          outer_error=float(np.sqrt(np.mean(errors**2)))))
        distance[(xx-center[0])**2+(yy-center[1])**2 < (1.8*radius)**2] = 0
    if max(lobe['radius'] for lobe in lobes) > 1.8*min(lobe['radius'] for lobe in lobes):
        raise DetectionError("Detected lobes have inconsistent sizes. Check Pairs or measure manually.")
    return lobes


def conductor_circle(rgb, lobe, insulation_mask):
    """Find a central circular color transition, then fit sampled edge points."""
    mask = cv2.morphologyEx(insulation_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    candidates = []
    for i, contour in enumerate(contours):
        if hierarchy[0, i, 3] < 0 or len(contour) < 30:
            continue
        points = contour[:, 0].astype(float)
        c, r, errors = circle_fit(points)
        if (lobe['radius']*.28 < r < lobe['radius']*.60
                and np.linalg.norm(c-lobe['center']) < lobe['radius']*.3
                and np.sqrt(np.mean(errors**2)) < r*.13
                and cv2.contourArea(contour) > np.pi*r*r*.8):
            candidates.append((np.linalg.norm(c-lobe['center']), points, c, r))
    if candidates:
        _, points, c, r = min(candidates, key=lambda item: item[0])
        lobe.update(conductor=points, conductor_center=c, conductor_radius=r,
                    method='color boundary')
        return
    lab = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB), (5, 5), 1).astype(np.float32)
    center, outer_radius = lobe['center'], lobe['radius']
    angles = np.linspace(0, 2*np.pi, 120, endpoint=False)
    directions = np.column_stack((np.cos(angles), np.sin(angles)))
    radii = np.arange(outer_radius*.27, outer_radius*.60, 1.)
    delta = max(2., outer_radius*.035)

    def scores(c):
        locations = c + directions[:, None, :] * radii[None, :, None]
        inner = sample(lab, locations-directions[:, None, :]*delta)
        outer = sample(lab, locations+directions[:, None, :]*delta)
        contrast = np.linalg.norm(outer-inner, axis=2)
        return np.median(contrast, axis=0), locations, contrast

    # Prefer an edge-supported Hough circle over internal copper texture.
    gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (5, 5), 1.5)
    x0, y0 = np.maximum(0, (center-outer_radius*.8).astype(int))
    x1, y1 = np.minimum(np.array(gray.shape[::-1]), (center+outer_radius*.8).astype(int))
    seed = None
    for threshold in (32, 28, 24, 20):
        circles = cv2.HoughCircles(gray[y0:y1, x0:x1], cv2.HOUGH_GRADIENT, 1,
                                  outer_radius*.5, param1=80, param2=threshold,
                                  minRadius=int(outer_radius*.28),
                                  maxRadius=int(outer_radius*.58))
        if circles is not None:
            for cx, cy, r in circles[0]:
                c = np.array([cx+x0, cy+y0])
                if np.linalg.norm(c-center) < outer_radius*.25:
                    seed = (c, r)
                    break
        if seed is not None:
            break
    search_center = center if seed is None else seed[0]
    if seed is not None:
        radii = np.arange(seed[1]-3, seed[1]+3.1, .75)
    best = None
    search_range = outer_radius*.18 if seed is None else 2.
    for dy in np.linspace(-search_range, search_range, 9 if seed is None else 3):
        for dx in np.linspace(-search_range, search_range, 9 if seed is None else 3):
            c = search_center + [dx, dy]
            score, _, _ = scores(c)
            i = int(np.argmax(score))
            if best is None or score[i] > best[0]:
                best = (float(score[i]), c, radii[i])
    quality, center, radius = best
    _, locations, contrast = scores(center)
    near = np.abs(radii-radius) < max(3, outer_radius*.055)
    indices = np.argmax(np.where(near[None, :], contrast, -1), axis=1)
    points = locations[np.arange(len(angles)), indices]
    strengths = contrast[np.arange(len(angles)), indices]
    points = points[strengths >= max(8., np.percentile(strengths, 20))]
    if quality < 8 or len(points) < 50:
        raise DetectionError("The conductor boundary is unclear. Reflections or an empty cavity may require manual measurement.")
    c, r, errors = circle_fit(points)
    points = points[errors < max(2.5, np.median(errors)*2.8)]
    c, r, errors = circle_fit(points)
    if np.linalg.norm(c-lobe['center'])+r >= outer_radius:
        raise DetectionError("The proposed conductor is outside its insulation.")
    lobe['conductor'] = points
    lobe['conductor_center'] = c
    lobe['conductor_radius'] = r
    lobe['contrast'] = quality
    lobe['method'] = 'edge estimate - review carefully'


def bridge_points(mask, a, b):
    axis = b['center']-a['center']
    length = np.linalg.norm(axis)
    axis /= length
    normal = np.array([-axis[1], axis[0]])
    # Sample the central neck perpendicular to the line of centers.
    widths = []
    neck_fraction = np.clip(.5+(a['radius']-b['radius'])/(2*length), .35, .65)
    for fraction in np.linspace(neck_fraction-.03, neck_fraction+.03, 15):
        center = a['center']+axis*length*fraction
        extent = min(a['radius'], b['radius'])*.75
        positions = np.arange(-extent, extent+1, .5)
        points = center+positions[:, None]*normal
        inside = sample(mask, points[None, :, :])[0] >= 128
        middle = int(np.argmin(np.abs(positions)))
        if not inside[middle]:
            continue
        left = middle
        right = middle
        while left > 0 and inside[left-1]:
            left -= 1
        while right < len(inside)-1 and inside[right+1]:
            right += 1
        width = positions[right]-positions[left]
        if left > 0 and right < len(inside)-1 and width >= 2:
            widths.append((width, points[[left, right]]))
    if len(widths) < 6:
        return None
    # Median, rather than an isolated dark scratch or glare in one cross-section.
    return sorted(widths, key=lambda item: item[0])[len(widths)//2][1]


def detect_pairs(image, pair_count):
    """Return ordered green/yellow proposals in original image coordinates."""
    if not 1 <= pair_count <= 12:
        raise DetectionError("Automatic detection supports 1 to 12 pairs.")
    rgb = np.asarray(image)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise DetectionError("Automatic detection requires a color photograph.")
    rgb = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
    factor = min(1., 1280./max(rgb.shape[:2]))
    if factor < 1:
        rgb = cv2.resize(rgb, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    kernel_size = max(5, int(min(rgb.shape[:2])*.018) | 1)
    green_raw, green = color_mask(hsv, (35, 60, 40), (95, 255, 255), kernel_size)
    yellow_raw, yellow = color_mask(hsv, (17, 90, 60), (35, 255, 255), kernel_size)
    greens = outer_circles(green, pair_count)
    yellows = outer_circles(yellow, pair_count)
    combined = cv2.morphologyEx(green_raw | yellow_raw, cv2.MORPH_CLOSE,
                               np.ones((5, 5), np.uint8))
    edges = {}
    for i, a in enumerate(greens):
        for j, b in enumerate(yellows):
            spacing = np.linalg.norm(a['center']-b['center'])
            if not 1.5 < spacing/min(a['radius'], b['radius']) < 3.5:
                continue
            tab = bridge_points(combined, a, b)
            if tab is not None:
                edges[i, j] = (spacing, tab)

    @lru_cache(None)
    def match(i, used):
        if i == pair_count:
            return 0., ()
        best = (float('inf'), ())
        for j in range(pair_count):
            if used & (1 << j) or (i, j) not in edges:
                continue
            cost, tail = match(i+1, used | (1 << j))
            candidate = (cost+edges[i, j][0], (j,)+tail)
            if candidate[0] < best[0]:
                best = candidate
        return best

    cost, assignment = match(0, 0)
    if not np.isfinite(cost):
        raise DetectionError("Could not identify the bridges between all pairs. Check Pairs or use manual measurement.")
    results = []
    for i, j in enumerate(assignment):
        a, b = greens[i], yellows[j]
        conductor_circle(rgb, a, green_raw)
        conductor_circle(rgb, b, yellow_raw)
        results.append(dict(lobes=[a, b], tab=edges[i, j][1]))
    results.sort(key=lambda pair: tuple(np.mean([l['center'] for l in pair['lobes']], axis=0)[::-1]))
    for pair in results:
        # Side 1 is the leftmost lobe, matching the manual view convention.
        pair['lobes'].sort(key=lambda lobe: lobe['center'][0])
        pair['tab'] /= factor
        for lobe in pair['lobes']:
            for field in ('center', 'radius', 'outer', 'outer_error', 'conductor',
                          'conductor_center', 'conductor_radius'):
                lobe[field] /= factor
    return results
