"""병사와 망루의 한 걸음 (numba). 병사 상태는 sim.entities 참고.

자연: 숲 속의 병사는 화살을 덜 맞는다 (cover). 걷는 속도는 지형을 따른다 (평지 1, 숲·습지·산은 느리다).
날고 있는 병사 (uair, 움직이거나 싸우는 용기사): 지형·물을 무시하고 곧장 (utx, uty)로 간다. 근접 병종은 이들을 칠 수 없다.
범위 피해 (k_splash): 맞은 자리 둘레의 적에게도 피해를 주고, 맞은 병사는 잠시 느려진다 (uslow).
야생 (neutral 나라): 병사와 망루가 저절로 덤비지 않는다 (명령을 받아야 친다).
외교 (sim/diplomacy.py): friend[a, b]면 같은 편 (자기 나라, 동맹)이라 서로 치지 않는다. 받는 피해는 hurt[나라]배 (배신자).
hits[a, b]에 a가 b에게 입힌 피해를 더한다 (관계에 반영).
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
         utx, uty, uslow, uair,
         nb, bx, by, bkind, bown, bhp, br, bprog, bcd, balive,
         k_speed, k_range, k_dmg, k_cd, k_sight, k_ranged, k_terrain, k_charge, k_vs, k_splash,
         walk, speed_mul, cover, fields, ready, tower_kind, tower_range, tower_dmg, tower_cd, neutral,
         shots, builders, friend, hurt, hits, blast, fx_speed, fx_take, fx_deal, ufreeze):
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
        if ufreeze[i] > 0:                           # 얼어붙었다 (드래곤 눈보라): 못 움직이고 못 친다
            ufreeze[i] -= dt
            umoving[i] = False
            continue
        k = ukind[i]
        o = uown[i]
        ucd[i] -= dt
        usearch[i] -= dt
        if uslow[i] > 0:
            uslow[i] -= dt
        st = ustate[i]
        fly = uair[i]
        # 정해 준 목표가 사라졌으면 쉰다
        if st == ATTACK:
            if (utgt[i] >= 0 and (not ualive[utgt[i]] or uaboard[utgt[i]] or (uair[utgt[i]] and not k_ranged[k]))) or (utgb[i] >= 0 and not balive[utgb[i]]) or (utgt[i] < 0 and utgb[i] < 0):
                ustate[i] = IDLE
                utgt[i] = -1
                utgb[i] = -1
                st = IDLE
        engage = (st == IDLE or st == AMOVE) and o != neutral
        sight = k_sight[k]
        if engage:
            t = utgt[i]
            if t >= 0 and (not ualive[t] or uaboard[t] or (uair[t] and not k_ranged[k])
                           or (ux[t] - ux[i]) ** 2 + (uy[t] - uy[i]) ** 2 > (sight * 1.4) ** 2):
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
                            if friend[o, uown[j]] == 0 and uown[j] != neutral and not (uair[j] and not k_ranged[k]):
                                d = (ux[j] - ux[i]) ** 2 + (uy[j] - uy[i]) ** 2
                                if d < bd:
                                    best, bd = j, d
                            j = nxt[j]
                utgt[i] = best
                if best < 0:
                    bbest, bbd = -1, sight * sight
                    for b in range(nb):
                        if balive[b] and friend[o, bown[b]] == 0:
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
                    dmg = k_dmg[k] * fx_deal[i]     # 기후: 사막 부족은 설원 밖에서 더 세게 (sim/climate.py)
                    if umoving[i]:                  # 달려와서 처음 치는 한 방 (기병 돌격)
                        dmg *= k_charge[k]
                    if utgt[i] >= 0:
                        dmg *= k_vs[k, ukind[t]]    # 상성 (보병 → 기병, 기병 → 궁수)
                        if k_ranged[k]:
                            dmg *= cover[int(uy[t]), int(ux[t])]
                        dmg *= hurt[uown[t]] * fx_take[t]   # 기후: 설원 부족은 사막 밖에서 덜 다친다
                        uhp[t] -= dmg
                        hits[o, uown[t]] += dmg
                        if uhp[t] <= 0:
                            ualive[t] = False
                        if k_splash[k] > 0:
                            uslow[t] = 2.5
                    else:
                        dmg *= hurt[bown[t]]
                        bhp[t] -= dmg
                        hits[o, bown[t]] += dmg
                        blast[t] = o                # 마지막으로 친 나라 (무너지면 창고 몫을 가져간다)
                    if k_splash[k] > 0:                 # 서리 숨결: 둘레의 적도 (덜) 맞고 느려진다
                        sr = k_splash[k]
                        scx, scy = int(tx) // CELL, int(ty) // CELL
                        for gy in range(max(scy - 1, 0), min(scy + 2, gh)):
                            for gx in range(max(scx - 1, 0), min(scx + 2, gw)):
                                j = head[gy * gw + gx]
                                while j >= 0:
                                    if j != utgt[i] and ualive[j] and not uaboard[j] and friend[o, uown[j]] == 0 and not uair[j] \
                                            and (ux[j] - tx) ** 2 + (uy[j] - ty) ** 2 <= sr * sr:
                                        uhp[j] -= dmg * 0.6 * hurt[uown[j]] * fx_take[j]
                                        hits[o, uown[j]] += dmg * 0.6
                                        uslow[j] = 2.5
                                        if uhp[j] <= 0:
                                            ualive[j] = False
                                    j = nxt[j]
                    if ns < shots.shape[0]:
                        shots[ns, 0], shots[ns, 1], shots[ns, 2], shots[ns, 3], shots[ns, 4] = ux[i], uy[i], tx, ty, 3 if k_splash[k] > 0 else (1 if k_ranged[k] else 0)
                        ns += 1
            elif st == ATTACK and uslot[i] >= 0 and dist > sight and ready[uslot[i]]:
                dx, dy, _, _ = _downhill(fields[uslot[i]], ux[i], uy[i], H, W)   # 멀면 길을 따라간다
            else:
                dx, dy = ddx, ddy
        elif fly and (st == MOVE or st == AMOVE):  # 날아서 곧장
            ddx, ddy = utx[i] - ux[i], uty[i] - uy[i]
            if ddx * ddx + ddy * ddy < 0.64:
                ustate[i] = IDLE
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
                    if j != i and ualive[j] and uair[j] == fly and uown[i] != neutral + 1:   # 나는 것끼리, 걷는 것끼리만 밀어낸다 (야생 드래곤은 밀리지 않는다: 뒷걸음질처럼 보이지 않게)
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
        sp = k_speed[k] if fly else k_speed[k] * speed_mul[int(uy[i]), int(ux[i])] ** k_terrain[k] * fx_speed[i]   # 지형 (병종마다) × 기후
        if uslow[i] > 0:
            sp *= 0.55                              # 서리 숨결에 맞아 느려짐
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
        if fly:
            if 0 <= nx_ < W and 0 <= ny_ < H:
                ux[i], uy[i] = nx_, ny_
        elif 0 <= nx_ < W and 0 <= ny_ < H and walk[int(ny_), int(nx_)]:
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
                    if ualive[j] and friend[bown[b], uown[j]] == 0 and uown[j] != neutral:
                        d = (ux[j] - bx[b]) ** 2 + (uy[j] - by[b]) ** 2
                        if d < bd:
                            best, bd = j, d
                    j = nxt[j]
        if best >= 0:
            bcd[b] = tower_cd
            dd = tower_dmg * cover[int(uy[best]), int(ux[best])] * hurt[uown[best]] * fx_take[best]
            uhp[best] -= dd
            hits[bown[b], uown[best]] += dd
            if uhp[best] <= 0:
                ualive[best] = False
            if ns < shots.shape[0]:
                shots[ns, 0], shots[ns, 1], shots[ns, 2], shots[ns, 3], shots[ns, 4] = bx[b], by[b] - 3, ux[best], uy[best], 1
                ns += 1
    return ns
