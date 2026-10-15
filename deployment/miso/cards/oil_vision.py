#!/usr/bin/env python3
"""Fixed-camera, manually selected ROI; deterministic needle segmentation (no AI).
Requires numpy and Pillow. Usage: python read-oiltank.py IMAGE [--overlay FILE]
Scale: clockwise from 8 o'clock (empty), through 12, to 4 (full).
"""
import argparse
import json
import math
from collections import deque
import numpy as np
from PIL import Image, ImageDraw


def measure(image, threshold):
    gray = np.asarray(image.convert('L'))
    h, w = gray.shape
    # Calibration selects only the needle area of the central white dial.
    x0, y0, x1, y1 = round(w*.455), round(h*.385), round(w*.61), round(h*.665)
    mask = gray[y0:y1, x0:x1] < threshold
    yy, xx = np.indices(mask.shape)
    mask &= (xx+x0-w*.533)**2 + (yy+y0-h*.523)**2 < (w*.068)**2
    seen = np.zeros_like(mask)
    components = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        q = deque([(y, x)]); seen[y, x] = True; points = []
        while q:
            yy, xx = q.popleft(); points.append((yy, xx))
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = yy+dy, xx+dx
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx] = True; q.append((ny,nx))
        components.append(points)
    components = [p for p in components if any(abs(x+x0-w*.533)<w*.008 and abs(y+y0-h*.523)<h*.014 for y,x in p)]
    if not components:
        raise ValueError('Spindle missing')
    points = np.array(max(components, key=len))
    if len(points) < 100:
        raise ValueError('Needle not found')
    component = np.zeros_like(mask); component[points[:,0], points[:,1]] = True
    # Last surviving erosion identifies the thick round spindle, not the tip.
    eroded = component.copy(); core = eroded
    while eroded.any():
        core = eroded
        pad = np.pad(eroded, 1)
        eroded = np.logical_and.reduce([pad[dy:dy+mask.shape[0],dx:dx+mask.shape[1]] for dy in range(3) for dx in range(3)])
    cy, cx = np.mean(np.argwhere(core), axis=0)
    if not (.52*w < cx+x0 < .545*w and .50*h < cy+y0 < .54*h):
        raise ValueError("Detected component does not contain the calibrated spindle")
    xy = points[:,::-1].astype(float)
    center = np.array([cx,cy])
    # The long end is the pointer; the shorter end is the counterweight.
    distances = np.linalg.norm(xy-center, axis=1)
    tip = xy[np.argmax(distances)]
    ray = tip-center
    outer = xy[(xy-center) @ (ray/np.linalg.norm(ray)) > np.linalg.norm(ray)*.35]
    _, vectors = np.linalg.eigh(np.cov(outer.T))
    direction = vectors[:,-1]
    if direction @ ray < 0:
        direction = -direction
    angle = math.degrees(math.atan2(direction[0], -direction[1])) % 360
    sweep = (angle-240) % 360
    if sweep > 358:
        sweep = 0
    elif 240 < sweep <= 242:
        sweep = 240
    elif sweep > 240:
        raise ValueError('Needle outside calibrated sweep')
    return {'threshold':threshold,'angle_clockwise_from_12_deg':round(angle,2),
            'percent_of_gauge_scale':round(sweep/240*100,2),
            'hub_px':(center+[x0,y0]).tolist(), 'tip_px':(tip+[x0,y0]).tolist(),
            'segmented_pixels':len(points)}


def read_level(image):
    results = []
    for threshold in (130, 145, 160, 175):
        try:
            results.append(measure(image, threshold))
        except ValueError:
            pass
    if len(results) < 3:
        raise ValueError('Insufficient consistent segmentations')
    values = sorted(r['percent_of_gauge_scale'] for r in results)
    # A dark threshold can retain only the spindle and a short needle fragment.
    # Require three thresholds to agree; never average an isolated fragment in.
    clusters = [values[i:j] for i in range(len(values))
                for j in range(i + 3, len(values) + 1)
                if values[j - 1] - values[i] <= 2]
    if not clusters:
        raise ValueError('Segmentations disagree')
    if max(float(np.median(c)) for c in clusters) - min(float(np.median(c)) for c in clusters) > 2:
        raise ValueError('Ambiguous segmentation consensus')
    values = max(clusters, key=lambda c: (len(c), -(max(c) - min(c))))
    value = float(np.median(values))
    return {'percent': int(math.floor(value + .5)), 'rawPercent': round(value, 2),
            'spread': round(max(values)-min(values), 2), 'method': 'needle-angle-v1'}
