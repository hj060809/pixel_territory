"""병사와 망루의 한 걸음 (numba). 병사 상태는 sim.entities 참고.

자연: 숲 속의 병사는 화살을 덜 맞는다 (cover). 걷는 속도는 지형을 따른다 (평지 1, 숲·습지·산은 느리다).
"""
from __future__ import annotations

import numpy as np
from numba import njit

from sim.entities import AMOVE, ATTACK, BUILD, IDLE, MOVE

CELL = 8


@njit(cache=True, nogil=True)
def _downhill(f, x, y, H, W):
    """거리 지도에서 주변 8칸 중 가장 가까운 쪽 방향. 반환 (dx, dy, 지금 거리, 더 나은 칸이 있나)."""
    iy, ix = int(y), int(x)
    cur = f[iy, ix]
    best = cur
    dx, dy = 0.0, 0.0
    for oy in range(-1, 2):
        for ox in range(-1, 2):
            yy, xx = iy + oy, ix + ox
            if 0 <= yy < H and 0 <= xx < W and f[yy, xx] < best:
                best = f[yy, xx]
                dx, dy = xx + 0.5 - x, yy + 0.5 - y
    return dx, dy, cur, best < cur


@njit(cache=True, nogil=True)
def step(dt, n, ux, uy, uhp, uown, ukind, ustate, uslot, utgt, utgb, ubld, ucd, usearch, uanim, umoving, ualive, uaboard,
         nb, bx, by, bkind, bown, bhp, br, bprog, bcd, balive,
         k_speed, k_range, k_dmg, k_cd, k_sight, k_ranged,
         walk, speed_mul, cover, fields, ready, tower_kind, tower_range, tower_dmg, tower_cd,
         shots, builders):
    H, W = walk.shape
    gw = W // CELL + 1
    gh = H // CELL + 1
    head = np.full(gw * gh, -1, np.int32)
    nxt = np.full(n, -1, np.int32)
    for i in range(n):
        if ualive[i] and not uaboard[i]:
            c = int(uy[i]) // CELL * gw + int(ux[i]) // CELL
            nxt[i] = head[c]
            head[c] = i
    ns = 0
    for b in range(nb):
        builders[b] = 0

    for i in range(n):
        if not ualive[i] or uaboard[i]:
            umoving[i] = False
            continue
        k = ukind[i]
        o = uown[i]
        ucd[i] -= dt
        usearch[i] -= dt
        st = ustate[i]
        # 정해 준 목표가 사라졌으면 쉰다
        if st == ATTACK:
            if (utgt[i] >= 0 and (not ualive[utgt[i]] or uaboard[utgt[i]])) or (utgb[i] >= 0 and not balive[utgb[i]]) or (utgt[i] < 0 and utgb[i] < 0):
                ustate[i] = IDLE
                utgt[i] = -1
                utgb[i] = -1
                st = IDLE
        engage = st == IDLE or st == AMOVE
        sight = k_sight[k]
        if engage:
            t = utgt[i]
            if t >= 0 and (not ualive[t] or uaboard[t] or (ux[t] - ux[i]) ** 2 + (uy[t] - uy[i]) ** 2 > (sight * 1.4) ** 2):
                utgt[i] = -1
            tb = utgb[i]
            if tb >= 0 and not balive[tb]:
                utgb[i] = -1
            if utgt[i] < 0 and usearch[i] <= 0:
                usearch[i] = 0.35 + (i % 7) * 0.03
                best, bd = -1, sight * sight
                cx, cy = int(ux[i]) // CELL, int(uy[i]) // CELL
                rr = int(sight) // CELL + 1
                for gy in range(max(cy - rr, 0), min(cy + rr + 1, gh)):
                    for gx in range(max(cx - rr, 0), min(cx + rr + 1, gw)):
                        j = head[gy * gw + gx]
                        while j >= 0:
                            if uown[j] != o:
                                d = (ux[j] - ux[i]) ** 2 + (uy[j] - uy[i]) ** 2
                                if d < bd:
                                    best, bd = j, d
                            j = nxt[j]
                utgt[i] = best
                if best < 0:
                    bbest, bbd = -1, sight * sight
                    for b in range(nb):
                        if balive[b] and bown[b] != o:
                            d = (bx[b] - ux[i]) ** 2 + (by[b] - uy[i]) ** 2 - br[b] * br[b]
                            if d < bbd:
                                bbest, bbd = b, d
                    utgb[i] = bbest
                else:
                    utgb[i] = -1
        # 움직일 방향
        dx, dy = 0.0, 0.0
        fight = (engage or st == ATTACK) and (utgt[i] >= 0 or utgb[i] >= 0)
        if fight:
            if utgt[i] >= 0:
                t = utgt[i]
                tx, ty, rad = ux[t], uy[t], 0.0
            else:
                t = utgb[i]
                tx, ty, rad = bx[t], by[t], br[t]
            ddx, ddy = tx - ux[i], ty - uy[i]
            dist = np.sqrt(ddx * ddx + ddy * ddy) - rad
            if dist <= k_range[k]:
                if ucd[i] <= 0:
                    ucd[i] = k_cd[k]
                    dmg = k_dmg[k]
                    if utgt[i] >= 0:
                        if k_ranged[k]:
                            dmg *= cover[int(uy[t]), int(ux[t])]
                        uhp[t] -= dmg
                        if uhp[t] <= 0:
                            ualive[t] = False
                    else:
                        bhp[t] -= dmg
                    if ns < shots.shape[0]:
                        shots[ns, 0], shots[ns, 1], shots[ns, 2], shots[ns, 3], shots[ns, 4] = ux[i], uy[i], tx, ty, k
                        ns += 1
            elif st == ATTACK and uslot[i] >= 0 and dist > sight and ready[uslot[i]]:
                dx, dy, _, _ = _downhill(fields[uslot[i]], ux[i], uy[i], H, W)   # 멀면 길을 따라간다
            else:
                dx, dy = ddx, ddy
        elif (st == MOVE or st == AMOVE or st == BUILD) and uslot[i] >= 0 and not ready[uslot[i]]:
            pass                                    # 거리 지도를 계산하는 중: 이번 걸음은 제자리에서 기다린다
        elif (st == MOVE or st == AMOVE or st == BUILD) and uslot[i] >= 0:
            f = fields[uslot[i]]
            iy, ix = int(uy[i]), int(ux[i])
            cur = f[iy, ix]
            arrive = 1.5
            if st == BUILD and ubld[i] >= 0:
                b = ubld[i]
                if not balive[b] or bprog[b] >= 1.0:
                    ustate[i] = IDLE
                    uslot[i] = -1
                    ubld[i] = -1
                elif (bx[b] - ux[i]) ** 2 + (by[b] - uy[i]) ** 2 <= (br[b] + 3.0) ** 2:
                    builders[b] += 1
                    cur = 0.0
                    arrive = 1e9
            if cur <= arrive and st != BUILD:
                ustate[i] = IDLE
                uslot[i] = -1
            elif cur < 1e29 and arrive < 1e8:
                dx, dy, _, better = _downhill(f, ux[i], uy[i], H, W)
                if not better and st != BUILD:      # 막혔으면 쉰다
                    ustate[i] = IDLE
                    uslot[i] = -1
            elif cur >= 1e29 and st != BUILD:
                ustate[i] = IDLE
                uslot[i] = -1
        # 서로 밀어내기
        sx, sy = 0.0, 0.0
        cx, cy = int(ux[i]) // CELL, int(uy[i]) // CELL
        for gy in range(max(cy - 1, 0), min(cy + 2, gh)):
            for gx in range(max(cx - 1, 0), min(cx + 2, gw)):
                j = head[gy * gw + gx]
                while j >= 0:
                    if j != i and ualive[j]:
                        ex, ey = ux[i] - ux[j], uy[i] - uy[j]
                        d2 = ex * ex + ey * ey
                        if d2 < 2.2 and d2 > 1e-6:
                            w = (2.2 - d2) / 2.2
                            sx += ex / np.sqrt(d2) * w
                            sy += ey / np.sqrt(d2) * w
                        elif d2 <= 1e-6:
                            sx += (np.random.random() - 0.5)
                            sy += (np.random.random() - 0.5)
                    j = nxt[j]
        L = np.sqrt(dx * dx + dy * dy)
        sp = k_speed[k] * speed_mul[int(uy[i]), int(ux[i])]
        vx, vy = 0.0, 0.0
        if L > 1e-6:
            vx, vy = dx / L * sp, dy / L * sp
        vx += sx * 2.0
        vy += sy * 2.0
        umoving[i] = L > 1e-6
        if umoving[i]:
            uanim[i] += dt * sp * 1.2
        # 저장하는 정밀도(float32)로 먼저 맞춘다: 191.9999가 저장되며 192.0(옆 물 칸)이 되지 않게
        nx_, ny_ = np.float32(ux[i] + vx * dt), np.float32(uy[i] + vy * dt)
        if 0 <= nx_ < W and 0 <= ny_ < H and walk[int(ny_), int(nx_)]:
            ux[i], uy[i] = nx_, ny_
        elif 0 <= nx_ < W and walk[int(uy[i]), int(nx_)]:
            ux[i] = nx_
        elif 0 <= ny_ < H and walk[int(ny_), int(ux[i])]:
            uy[i] = ny_

    # 망루: 사거리 안의 가장 가까운 적 병사를 쏜다
    rr = int(tower_range) // CELL + 1
    for b in range(nb):
        if not balive[b] or bkind[b] != tower_kind or bprog[b] < 1.0:
            continue
        bcd[b] -= dt
        if bcd[b] > 0:
            continue
        best, bd = -1, tower_range * tower_range
        cx, cy = int(bx[b]) // CELL, int(by[b]) // CELL
        for gy in range(max(cy - rr, 0), min(cy + rr + 1, gh)):
            for gx in range(max(cx - rr, 0), min(cx + rr + 1, gw)):
                j = head[gy * gw + gx]
                while j >= 0:
                    if ualive[j] and uown[j] != bown[b]:
                        d = (ux[j] - bx[b]) ** 2 + (uy[j] - by[b]) ** 2
                        if d < bd:
                            best, bd = j, d
                    j = nxt[j]
        if best >= 0:
            bcd[b] = tower_cd
            uhp[best] -= tower_dmg * cover[int(uy[best]), int(ux[best])]
            if uhp[best] <= 0:
                ualive[best] = False
            if ns < shots.shape[0]:
                shots[ns, 0], shots[ns, 1], shots[ns, 2], shots[ns, 3], shots[ns, 4] = bx[b], by[b] - 3, ux[best], uy[best], 1
                ns += 1
    return ns
