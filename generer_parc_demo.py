#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genere le parc FICTIF de demonstration : data/*.csv + data/config.json.

400 engins inventes de toutes pieces : 300 camions (compteurs km) et
100 engins de chantier (compteurs horaires), sur novembre 2026, avec les
etats et les defauts qu'on rencontre vraiment dans des pointages saisis
a la main : 1/2 postes, stand-by, entrepose, jours de panne coherents
avec le journal des pannes, dimanches feries, lectures manquantes,
doublons, journees invraisemblables, compteurs qui reculent, sauts de
compteur, unites a confirmer, machines arrivees en cours de mois.

Aucune donnee reelle : chaque chiffre sort d'un generateur pseudo-
aleatoire a graine fixe (reproductible a l'identique).

    python3 generer_parc_demo.py            # ecrit data/
"""

import calendar
import csv
import json
import random
from pathlib import Path

GRAINE = 202611
ANNEE, MOIS = 2026, 11
DERNIER_JOUR_SAISI = 21          # releves du 1er au 21 novembre
CHANTIERS = ["CH-ATLAS", "CH-RIF", "CH-SOUSS", "DEPOT-CENTRAL"]
TYPES_PANNES = ["Hydraulique", "Electrique", "Moteur", "Freinage", "Pneus"]
PANNES_DESC = {
    "Hydraulique": ["Fuite flexible", "Joint de verin", "Pompe lente"],
    "Electrique": ["Batterie HS", "Alternateur", "Faisceau coupe"],
    "Moteur": ["Surchauffe", "Fumee noire", "Courroie"],
    "Freinage": ["Plaquettes usees", "Fuite liquide"],
    "Pneus": ["Crevaison", "Usure irreguliere"],
}

rng = random.Random(GRAINE)


def dimanches():
    return [j for j in range(1, DERNIER_JOUR_SAISI + 1)
            if calendar.weekday(ANNEE, MOIS, j) == 6]


def jours_ouvres():
    return [j for j in range(1, DERNIER_JOUR_SAISI + 1)
            if calendar.weekday(ANNEE, MOIS, j) != 6]


def plan_jours(p_travail, p_manquant, jours_panne=()):
    """Etat de chaque jour ouvre : (jour, etat, actif, manquant)."""
    panne = set(jours_panne)
    out = []
    for j in jours_ouvres():
        if j in panne:
            out.append((j, "P", False, False))
            continue
        if rng.random() < p_manquant:
            out.append((j, "", False, True))     # lecture manquante
            continue
        r = rng.random()
        if r < p_travail:
            out.append((j, "2" if rng.random() < 0.06 else "1", True, False))
        elif r < p_travail + 0.08:
            out.append((j, "SB", False, False))  # stand-by
        elif r < p_travail + 0.11:
            out.append((j, "E", False, False))   # entrepose
        else:
            out.append((j, "SB", False, False))
    return out


def main():
    racine = Path(__file__).resolve().parent
    data = racine / "data"
    data.mkdir(exist_ok=True)

    pointages = []   # (date, code, debut, fin, chantier, etat)
    vidanges = []    # (date, code, compteur_vidange)
    pannes = []      # (date, code, type, description, duree)
    config_engins = {}
    dims = set(dimanches())

    def engin(code, chantier, cpt0, plan, delta_actif, delta_repos=0.0,
              sauts=None, baisse=None):
        """Ecrit les lignes pointage selon le plan ; ajoute les dimanches F."""
        sauts = sauts or {}
        baisse = baisse or {}
        plan_map = {j: (etat, actif, manquant) for j, etat, actif, manquant in plan}
        cpt = cpt0
        for j in range(1, DERNIER_JOUR_SAISI + 1):
            date = f"{ANNEE}-{MOIS:02d}-{j:02d}"
            if j in dims:
                # dimanche ferie : compteur inchange, etat F
                pointages.append((date, code, f"{cpt:g}", f"{cpt:g}",
                                  chantier, "F"))
                continue
            etat, actif, manquant = plan_map[j]
            if manquant:
                pointages.append((date, code, "", "", chantier, ""))
                continue
            delta = delta_actif(etat) if actif else delta_repos
            if j in sauts:
                delta += sauts[j]
            if j in baisse:
                delta -= baisse[j]
            cpt_suiv = round(cpt + delta, 1)
            pointages.append((date, code, f"{cpt:g}", f"{cpt_suiv:g}",
                              chantier, etat))
            cpt = cpt_suiv
        return cpt

    # ---------- 300 camions : compteurs KILOMETRIQUES (declares en config)
    for i in range(1, 301):
        code = f"CAM-{i:03d}"
        chantier = CHANTIERS[i % len(CHANTIERS)]
        cpt0 = round(rng.uniform(20000, 240000))
        config_engins[code] = {"type_compteur": "km"}

        # pannes d'abord : le jour P du pointage sera coherent
        jours_panne = []
        if rng.random() < 0.18:
            for _ in range(rng.randint(1, 2)):
                j = rng.choice(jours_ouvres())
                jours_panne.append(j)
                t = rng.choice(TYPES_PANNES)
                pannes.append((f"{ANNEE}-{MOIS:02d}-{j:02d}", code, t,
                               rng.choice(PANNES_DESC[t]),
                               round(rng.uniform(0.5, 6), 1)))

        plan = plan_jours(p_travail=0.85, p_manquant=0.02,
                          jours_panne=jours_panne)
        sauts, baisse = {}, {}
        if i == 58 or i == 59:   # journee tres longue (> 800 km : a confirmer)
            sauts[jours_ouvres()[6]] = 900
        if i == 74:              # jour impossible (> 1500 km : invalide)
            sauts[jours_ouvres()[9]] = 2000
        if i == 37:              # compteur qui recule (remise a zero ?)
            baisse[jours_ouvres()[8]] = 800

        cpt_fin = engin(code, chantier, cpt0, plan,
                        lambda etat: rng.uniform(120, 450), sauts=sauts,
                        baisse=baisse)
        if i == 12:              # doublon de saisie
            j = jours_ouvres()[5]
            lig = [p for p in pointages if p[1] == code and
                   p[0] == f"{ANNEE}-{MOIS:02d}-{j:02d}"][0]
            pointages.append((lig[0], code, lig[2], lig[3], chantier, lig[5]))

        if rng.random() < 0.9:
            vidanges.append((f"{ANNEE}-{MOIS - 1:02d}-15", code,
                             f"{cpt_fin - rng.uniform(2000, 9500):g}"))

    # ---------- 96 engins de chantier : compteurs HORAIRES
    familles = [("BUL", 25), ("CHR", 30), ("EXC", 26), ("NIV", 15)]
    compte_global = 0
    for prefixe, nombre in familles:
        for i in range(1, nombre + 1):
            compte_global += 1
            code = f"{prefixe}-{100 + i}"
            chantier = CHANTIERS[compte_global % len(CHANTIERS)]
            cpt0 = round(rng.uniform(400, 19000))

            jours_panne = []
            if rng.random() < 0.3:
                for _ in range(rng.randint(1, 3)):
                    j = rng.choice(jours_ouvres())
                    jours_panne.append(j)
                    t = rng.choice(TYPES_PANNES)
                    pannes.append((f"{ANNEE}-{MOIS:02d}-{j:02d}", code, t,
                                   rng.choice(PANNES_DESC[t]),
                                   round(rng.uniform(0.5, 8), 1)))

            plan = plan_jours(p_travail=0.78, p_manquant=0.03,
                              jours_panne=jours_panne)
            sauts, baisse = {}, {}
            if compte_global % 23 == 0:      # saut isole > 24 h : invalide
                sauts[jours_ouvres()[10]] = rng.uniform(30, 70)
            if compte_global % 41 == 0:      # compteur qui recule
                baisse[jours_ouvres()[4]] = 25

            def delta_h(etat):
                # jour 2 postes : 12-15 h (signale "journee longue" si > 12)
                return rng.uniform(12, 15) if etat == "2" else rng.uniform(6, 10)

            cpt_fin = engin(code, chantier, cpt0, plan, delta_h,
                            sauts=sauts, baisse=baisse)

            if rng.random() < 0.85:
                vidanges.append((f"{ANNEE}-{MOIS - 1:02d}-10", code,
                                 f"{cpt_fin - rng.uniform(30, 260):g}"))

    # ---------- 4 engins aux releves km NON declares (dans les 100)
    # -> "unite a confirmer" : exclus des totaux, pas d'estimation
    for i in range(1, 5):
        code = f"MSC-90{i}"
        cpt0 = round(rng.uniform(30000, 90000))
        plan = plan_jours(p_travail=1.0, p_manquant=0.0)
        engin(code, CHANTIERS[i % len(CHANTIERS)], cpt0, plan,
              lambda etat: rng.uniform(150, 320))

    # ---------- 3 engins arrives en cours de mois : < 3 jours valides
    for code in ("EXC-125", "EXC-126", "NIV-115"):
        pointages[:] = [p for p in pointages if p[1] != code]
        cpt = round(rng.uniform(2000, 8000))
        for j in (20, 21):
            fin = round(cpt + rng.uniform(6, 9), 1)
            pointages.append((f"{ANNEE}-{MOIS:02d}-{j:02d}", code,
                              f"{cpt:g}", f"{fin:g}", "CH-ATLAS", "1"))
            cpt = fin

    # doublon + duree negative dans les pannes : montrent les exclusions
    pannes.append((f"{ANNEE}-{MOIS:02d}-05", "BUL-101", "Electrique",
                   "Relais demarreur", 2.0))
    pannes.append((f"{ANNEE}-{MOIS:02d}-05", "BUL-101", "Electrique",
                   "Relais demarreur", 2.0))
    pannes.append((f"{ANNEE}-{MOIS:02d}-08", "CHR-110", "Moteur",
                   "Saisie incoherente", -3.0))

    # vidange incoherente (compteur de vidange au-dessus du compteur actuel)
    vidanges.append((f"{ANNEE}-{MOIS:02d}-18", "NIV-101", "999999"))

    # ---------- ecriture
    pointages.sort(key=lambda p: (p[1], p[0]))
    with open(data / "pointage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "code_engin", "compteur_debut", "compteur_fin",
                    "chantier", "etat"])
        w.writerows(pointages)

    with open(data / "pannes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "code_engin", "type_panne", "description", "duree_arret_h"])
        w.writerows(sorted(pannes))

    with open(data / "vidanges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "code_engin", "compteur_vidange"])
        w.writerows(sorted(vidanges))

    config = {
        "intervalle_vidange_h_defaut": 250,
        "intervalle_vidange_km_defaut": 10000,
        "engins": config_engins,
    }
    with open(data / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=1)

    print(f"Parc fictif genere dans {data}/ :")
    print(f"  300 camions (km) + 96 engins (h) + 4 unites a confirmer = 400")
    print(f"  {len(pointages)} lignes de pointage, {len(pannes)} pannes, "
          f"{len(vidanges)} vidanges (graine {GRAINE}, reproductible)")


if __name__ == "__main__":
    main()
