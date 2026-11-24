#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Controle du pointage des engins + suivi des pannes et des vidanges.

Projet personnel de demonstration, sur donnees FICTIVES uniquement.
Un humain garde la decision finale : le script signale, il ne corrige
jamais les donnees d'origine et ne juge pas la cause d'une anomalie.

Utilisation :
    python3 main.py
    python3 main.py --data data --sortie rapports
"""

import argparse
import calendar
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

# Regles de controle (documentees, modifiables)
SEUIL_HEURES_JOUR_MAX = 24.0   # une lecture par jour : au-dela = invalide
SEUIL_HEURES_JOUR_REVUE = 12.0 # au-dela : signale a verifier, exclu des totaux
SEUIL_VIDANGE_BIENTOT_H = 20.0 # vidange "bientot" s'il reste moins de 20 h
# Memes regles pour les compteurs kilometriques declares (jamais devines) :
SEUIL_KM_JOUR_MAX = 1500.0     # au-dela : invalide meme en km
SEUIL_KM_JOUR_REVUE = 800.0    # au-dela : journee km a confirmer
SEUIL_KM_SAUT = 1000.0         # saut km liste dans le tableau de bord
SEUIL_VIDANGE_BIENTOT_KM = 500.0
VIDANGE_INTERVALLE_KM_DEFAUT = 10000.0
SAUTS_AVANT_UNITE_INCONNUE = 2  # sauts > seuil repetes : unite probablement mauvaise


def lire_csv(chemin):
    with open(chemin, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def date_from_iso(s):
    from datetime import date
    a, m, j = (int(x) for x in s.split("-"))
    return date(a, m, j)


def controler_pointages(lignes, types=None):
    """Controle chaque ligne de pointage.

    types : {code_engin: "h" ou "km"} declare dans la config, jamais devine.
    Un compteur kilometrique declare n'est pas soumis a la regle des 24 h
    (ses seuils km s'appliquent) ; sans declaration, tout est traite en h.

    Retourne une liste de dicts : champs d'origine + heures_calculees,
    statut et motif. Une ligne non OK est visible mais exclue des totaux
    et ne sert JAMAIS de compteur de reference pour les vidanges.
    """
    types = types or {}
    resultats = []
    vus = set()
    for row in lignes:
        code = row["code_engin"].strip()
        jour = row["date"].strip()
        debut = row["compteur_debut"].strip()
        fin = row["compteur_fin"].strip()
        etat = row.get("etat", "").strip()
        unite = "km" if types.get(code) == "km" else "h"
        seuil_max = SEUIL_KM_JOUR_MAX if unite == "km" else SEUIL_HEURES_JOUR_MAX
        seuil_revue = SEUIL_KM_JOUR_REVUE if unite == "km" else SEUIL_HEURES_JOUR_REVUE

        statut = "OK"
        motifs = []
        heures = None

        cle = (code, jour)
        if cle in vus:
            statut = "DOUBLON"
            motifs.append("doublon engin+date : exclu des totaux, jamais double-compte")
        vus.add(cle)

        if statut == "OK":
            if not debut or not fin:
                statut = "A_VERIFIER"
                motifs.append("lecture manquante : heures non calculees (jamais 0 par defaut)")
            else:
                try:
                    d0, d1 = float(debut), float(fin)
                    diff = round(d1 - d0, 1)
                    if diff < 0:
                        statut = "A_VERIFIER"
                        motifs.append("compteur final < debut : verifier la lecture ou une remise a zero")
                    elif etat in ("1", "2") and diff == 0:
                        statut = "A_VERIFIER"
                        motifs.append("etat travail sans hausse du compteur : a confirmer")
                    elif etat in ("P", "E", "SB", "F", "A", "D", "CP") and diff > 0:
                        statut = "A_VERIFIER"
                        motifs.append(f"hausse du compteur avec etat {etat} : a confirmer")
                        heures = diff
                    elif diff > seuil_max:
                        statut = "INVALIDE"
                        motifs.append(f"plus de {seuil_max:g} {unite} sur une journee (1 lecture/jour) : invalide")
                    elif diff > seuil_revue:
                        statut = "A_VERIFIER"
                        motifs.append(f"journee longue (> {seuil_revue:g} {unite}) : a confirmer")
                        heures = diff
                    else:
                        heures = diff
                except ValueError:
                    statut = "A_VERIFIER"
                    motifs.append("lecture non numerique")

        resultats.append({
            "date": jour,
            "code_engin": code,
            "chantier": row.get("chantier", "").strip(),
            "etat": etat,
            "compteur_debut": debut,
            "compteur_fin": fin,
            "heures_calculees": "" if heures is None else heures,
            "statut": statut,
            "motif": "; ".join(motifs),
        })
    return resultats


def totaux_hebdo(resultats, types=None):
    """Total valide par engin et par semaine ISO, dans l'unite de l'engin.

    Seules les lignes OK comptent. Les lignes signalees restent visibles
    dans le controle mais ne gonflent jamais un total. Heures et km ne
    sont jamais melanges : chaque ligne porte l'unite declaree de l'engin.
    """
    types = types or {}
    totaux = defaultdict(float)
    for r in resultats:
        if r["statut"] != "OK" or r["heures_calculees"] == "":
            continue
        an, sem, _ = date_from_iso(r["date"]).isocalendar()
        totaux[(r["code_engin"], f"{an}-S{sem:02d}")] += float(r["heures_calculees"])
    return [
        {"code_engin": k[0], "semaine": k[1], "heures_valides": round(v, 1),
         "unite": "km" if types.get(k[0]) == "km" else "h"}
        for k, v in sorted(totaux.items())
    ]


def compteur_actuel(resultats):
    """Dernier compteur VALIDE (ligne OK) par engin, et statut de la toute
    derniere ligne non DOUBLON.

    Retourne (actuels, dernier_statut) :
      actuels[code]        = (date_ok, compteur_ok)
      dernier_statut[code] = (date, statut) de la ligne la plus recente
    Une lecture invalide, inversee ou manquante ne pilote jamais un
    statut de vidange rassurant : on retombe sur le dernier compteur
    valide et on le dit.
    """
    actuels = {}
    dernier = {}
    for r in resultats:
        if r["statut"] == "DOUBLON":
            continue
        code = r["code_engin"]
        if code not in dernier or r["date"] >= dernier[code][0]:
            dernier[code] = (r["date"], r["statut"])
        if r["statut"] != "OK" or r["heures_calculees"] == "":
            continue
        fin = float(r["compteur_fin"])
        if code not in actuels or r["date"] >= actuels[code][0]:
            actuels[code] = (r["date"], fin)
    return actuels, dernier


def calculer_statut_vidange(compteur, derniere_vidange, intervalle, unite="h"):
    """Retourne (statut, restant) dans l'unite du compteur (h ou km).

    Compteur actuel inferieur au compteur de la derniere vidange =
    donnees incoherentes -> A_VERIFIER, jamais un OK calcule.
    """
    seuil_bientot = SEUIL_VIDANGE_BIENTOT_KM if unite == "km" else SEUIL_VIDANGE_BIENTOT_H
    faites = compteur - derniere_vidange
    restantes = round(intervalle - faites, 1)
    if faites < 0:
        return "A_VERIFIER", restantes
    if restantes <= 0:
        return "EN_RETARD", restantes
    if restantes <= seuil_bientot:
        return "BIENTOT", restantes
    return "OK", restantes


def suivi_vidanges(vidanges, resultats, config):
    intervalle_defaut = config.get("intervalle_vidange_h_defaut", 250)
    intervalle_km_defaut = config.get("intervalle_vidange_km_defaut",
                                     VIDANGE_INTERVALLE_KM_DEFAUT)
    engins_cfg = config.get("engins", {})
    actuels, dernier = compteur_actuel(resultats)

    dernieres = {}
    avertissements = []
    for v in vidanges:
        code = v["code_engin"].strip()
        try:
            cpt = float(v["compteur_vidange"])
        except (ValueError, TypeError):
            avertissements.append(f"vidange ignoree pour {code} : compteur non numerique")
            continue
        if code not in dernieres or cpt > dernieres[code]["compteur"]:
            dernieres[code] = {"date": v["date"], "compteur": cpt}

    lignes = []
    for code in sorted(set(list(actuels) + list(dernieres))):
        cfg_e = engins_cfg.get(code, {})
        unite = "km" if cfg_e.get("type_compteur") == "km" else "h"
        intervalle = cfg_e.get("intervalle_vidange_km" if unite == "km"
                               else "intervalle_vidange_h",
                               intervalle_km_defaut if unite == "km"
                               else intervalle_defaut)
        actuel = actuels.get(code)
        dern = dernieres.get(code)
        note = ""
        if actuel is None or dern is None:
            lignes.append({
                "code_engin": code,
                "compteur_actuel": actuel[1] if actuel else "",
                "derniere_vidange": dern["compteur"] if dern else "",
                "intervalle_h": intervalle, "heures_restantes": "",
                "unite": unite,
                "statut": "A_VERIFIER",
                "note": "historique incomplet : compteur valide ou vidange manquant",
            })
            continue
        statut, restantes = calculer_statut_vidange(actuel[1], dern["compteur"], intervalle,
                                                    unite=unite)
        d_date, d_statut = dernier.get(code, ("", ""))
        if d_statut not in ("", "OK"):
            note = (f"derniere lecture du {d_date} signalee ({d_statut}) : "
                    f"statut base sur le dernier compteur valide du {actuel[0]}")
        if statut == "A_VERIFIER" and not note:
            note = "compteur actuel < compteur de la derniere vidange : donnees incoherentes"
        lignes.append({
            "code_engin": code,
            "compteur_actuel": actuel[1],
            "derniere_vidange": dern["compteur"],
            "intervalle_h": intervalle,
            "heures_restantes": restantes,
            "unite": unite,
            "statut": statut,
            "note": note,
        })
    return lignes, avertissements


def synthese_pannes(pannes):
    """Frequence des pannes par engin et par type, plus duree d'arret.

    Seules les lignes VALIDES comptent : duree negative ou non numerique,
    code ou type manquant, doublon (meme date+engin+type) -> exclus et
    listes separement, jamais additionnes en silence.
    Indicateur de revue, pas un diagnostic technique.
    """
    par_engin = defaultdict(lambda: {"nb": 0, "arret_h": 0.0})
    par_type = defaultdict(lambda: {"nb": 0, "arret_h": 0.0})
    exclus = []
    vus = set()
    for p in pannes:
        code = p["code_engin"].strip()
        typ = p["type_panne"].strip()
        jour = p["date"].strip()
        brut = (p.get("duree_arret_h") or "").strip()
        motif = None
        if not code or not typ:
            motif = "code engin ou type de panne manquant"
        else:
            cle = (jour, code, typ)
            if cle in vus:
                motif = "doublon meme date+engin+type"
            vus.add(cle)
        duree = None
        if motif is None:
            try:
                duree = float(brut)
                if duree < 0:
                    motif = "duree d'arret negative"
            except ValueError:
                motif = "duree d'arret non numerique"
        if motif:
            exclus.append({"date": jour, "code_engin": code, "type_panne": typ, "motif": motif})
            continue
        par_engin[code]["nb"] += 1
        par_engin[code]["arret_h"] += duree
        par_type[(code, typ)]["nb"] += 1
        par_type[(code, typ)]["arret_h"] += duree
    detail = [
        {"code_engin": k[0], "type_panne": k[1], "nb_fois": v["nb"], "arret_total_h": round(v["arret_h"], 1)}
        for k, v in sorted(par_type.items(), key=lambda kv: (-kv[1]["nb"], kv[0]))
    ]
    return detail, par_engin, exclus


def ecrire_csv(chemin, lignes, champs):
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(lignes)


def _modele_depuis_csv(resultats, config):
    """Convertit le controle CSV de demonstration vers le modele du tableau de bord."""
    par_engin = {}
    for r in resultats:
        j = int(r["date"].split("-")[2])
        e = par_engin.setdefault(r["code_engin"], {"jours": {}, "compte_etats": {}, "total": 0.0})
        heures = None if r["heures_calculees"] == "" else float(r["heures_calculees"])
        etat = r.get("etat", "")
        if not etat:
            etat = "1" if r["statut"] in ("OK", "A_VERIFIER") and heures else ""
        e["jours"][j] = {
            "etat": etat, "compteur": None if not r["compteur_fin"] else float(r["compteur_fin"]),
            "heures": heures, "statut": r["statut"], "motif": r["motif"],
        }
        if etat:
            e["compte_etats"][etat] = e["compte_etats"].get(etat, 0) + 1
        if r["statut"] == "OK" and heures:
            e["total"] += heures
    cfg_engins = config.get("engins", {}) if config else {}
    engins = []
    anomalies = []
    for code, e in sorted(par_engin.items()):
        type_compteur = "km" if cfg_engins.get(code, {}).get("type_compteur") == "km" else "h"
        seuil_saut = SEUIL_KM_SAUT if type_compteur == "km" else SEUIL_HEURES_JOUR_MAX
        jours_present = [j for j, d in e["jours"].items() if d["compteur"] is not None]
        # sauts de compteur (meme regle que l'analyse des sources reelles)
        sauts = []
        prev_j = None
        for j in sorted(e["jours"]):
            c = e["jours"][j]["compteur"]
            if c is not None and prev_j is not None:
                delta = round(c - e["jours"][prev_j]["compteur"], 1)
                if delta > seuil_saut:
                    sauts.append({"jour": j, "de": e["jours"][prev_j]["compteur"],
                                  "vers": c, "saut": delta})
            if c is not None:
                prev_j = j
        # sauts repetes sur un compteur declare horaire = unite probablement
        # mauvaise : engin EXCLU des totaux, jamais redeclare automatiquement
        unite_inconnue = type_compteur == "h" and len(sauts) >= SAUTS_AVANT_UNITE_INCONNUE
        if unite_inconnue:
            e["total"] = 0.0
            for j, d in e["jours"].items():
                d["heures"] = None
                if d["statut"] == "OK" and d["compteur"] is not None:
                    d["statut"] = "A_VERIFIER"
                    d["motif"] = ("unite du compteur a confirmer "
                                  "(releves incompatibles avec des heures) : "
                                  "exclu des totaux")
        # estimation de fin de mois
        deltas_ok = [d["heures"] for j, d in sorted(e["jours"].items())
                     if d["statut"] == "OK" and d["heures"] is not None]
        affectation = ""
        for r in reversed([r for r in resultats if r["code_engin"] == code]):
            if r.get("chantier"):
                affectation = r["chantier"]
                break
        engins.append({
            "code": code, "societe": "", "affectation": affectation, "capacite": "",
            "type_compteur": type_compteur, "unite_inconnue": unite_inconnue,
            "jours": e["jours"], "total_heures": round(e["total"], 1) if type_compteur == "h" else 0,
            "total_km": round(e["total"], 1) if type_compteur == "km" else 0,
            "compte_etats": e["compte_etats"],
            "sauts": sauts,
            "_deltas_ok": deltas_ok,
            "derniere_lecture": max(jours_present) if jours_present else None,
        })
        for j, d in e["jours"].items():
            if d["statut"] != "OK":
                anomalies.append({"engin": code, "jour": j, "gravite": d["statut"], "motif": d["motif"]})
    dates = [r["date"] for r in resultats]
    annee, mois = (int(dates[0].split("-")[0]), int(dates[0].split("-")[1])) if dates else (None, None)
    for eng in engins:
        deltas_ok = eng.pop("_deltas_ok")
        eng["prevision"] = None
        if annee and mois and eng["derniere_lecture"]:
            # ancre = derniere lecture VALIDE ; rythme par jour calendaire
            jours_valides = [j for j, d in eng["jours"].items()
                             if d["statut"] == "OK" and d["compteur"] is not None]
            j_dernier = max(jours_valides) if jours_valides else None
            j_premier = min(j for j, d in eng["jours"].items()
                            if d["compteur"] is not None)
            if eng.get("unite_inconnue"):
                eng["prevision"] = {"raison": "unite du compteur a confirmer : "
                                               "pas d'estimation"}
            elif j_dernier is not None:
                restants = calendar.monthrange(annee, mois)[1] - j_dernier
                observe = j_dernier - j_premier
                c_dernier = eng["jours"][j_dernier]["compteur"]
                if restants > 0 and observe >= 1 and len(deltas_ok) >= 3:
                    heures_valides = sum(deltas_ok)
                    rythme = heures_valides / observe
                    eng["prevision"] = {
                        "dernier_compteur": c_dernier, "dernier_jour": j_dernier,
                        "rythme_jour": round(rythme, 1),
                        "heures_base": round(heures_valides, 1),
                        "jours_base": len(deltas_ok), "jours_observe": observe,
                        "jours_restants": restants,
                        "estimation": round(c_dernier + rythme * restants, 1),
                        "unite": eng["type_compteur"],
                    }
                elif restants > 0:
                    eng["prevision"] = {"raison": "donnees insuffisantes "
                                                   "(%d jour(s) valide(s)) : pas d'estimation"
                                                   % len(deltas_ok)}
    return {"source": "demo csv", "chantier": "Parc fictif de demonstration",
            "annee": annee, "mois": mois, "engins": engins, "anomalies": anomalies}


def main():
    ap = argparse.ArgumentParser(description="Controle pointage engins + pannes + vidanges + tableau de bord")
    ap.add_argument("--data", default="data", help="dossier des CSV d'entree")
    ap.add_argument("--sortie", default="rapports", help="dossier des sorties")
    ap.add_argument("--excel", help="etat Excel 'Fiche de pointage' telecharge (prive, hors depot)")
    ap.add_argument("--consulter", help="grille Consulter sauvegardee en HTML (privee, hors depot)")
    ap.add_argument("--fetch", action="store_true",
                    help="telecharge la grille Consulter via config.local.json (identifiants hors depot)")
    ap.add_argument("--config-fetch", default="config.local.json", help="fichier prive de connexion")
    ap.add_argument("--chantier-id", help="identifiant chantier du site, pour --fetch")
    ap.add_argument("--annee", type=int, help="annee du pointage (sources reelles)")
    ap.add_argument("--mois", type=int, help="mois du pointage (sources reelles)")
    args = ap.parse_args()

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    if args.excel or args.consulter or args.fetch:
        import pointage_import
        from dashboard import generer_dashboard

        if args.fetch:
            if not (args.chantier_id and args.annee and args.mois):
                ap.error("--fetch exige --chantier-id, --annee et --mois")
            import fetch_pointage
            html_path = fetch_pointage.telecharger_consulter(
                args.config_fetch, args.chantier_id, args.annee, args.mois,
                str(sortie / "consulter_grille.html"))
            print(f"Grille Consulter telechargee (lecture seule) -> {html_path}")
            source = pointage_import.parse_consulter_html(html_path)
        elif args.excel:
            source = pointage_import.parse_fiche_xlsx(args.excel)
        else:
            source = pointage_import.parse_consulter_html(args.consulter)

        config = {}
        cfg_path = Path(args.data) / "config.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                config = json.load(f)

        analyse = pointage_import.analyser(source, config, annee=args.annee, mois=args.mois)
        pointage_import.exporter_json(analyse, sortie / "analyse.json")
        generer_dashboard(analyse, sortie / "dashboard.html")

        from pointage_import import synthese
        k = synthese(analyse)
        print(f"Source : {source['type']} | chantier : {source.get('chantier') or '(du fichier)'}")
        print(f"{k['nb_engins']} engins | {k['heures_totales']} h valides | "
              f"{k['nb_pannes_jours']} jours panne | {k['nb_anomalies']} signalements")
        for a in analyse["anomalies"][:20]:
            print(f"  [{a['gravite']}] {a['engin']} jour {a['jour']} : {a['motif']}")
        print(f"Tableau de bord : {sortie / 'dashboard.html'}")
        return

    data = Path(args.data)
    pointages = lire_csv(data / "pointage.csv")
    pannes = lire_csv(data / "pannes.csv")
    vidanges = lire_csv(data / "vidanges.csv")
    with open(data / "config.json", encoding="utf-8") as f:
        config = json.load(f)

    types_declares = {c: cfg.get("type_compteur", "h")
                      for c, cfg in config.get("engins", {}).items()}
    resultats = controler_pointages(pointages, types=types_declares)
    totaux = totaux_hebdo(resultats, types=types_declares)
    vid, avert_vidanges = suivi_vidanges(vidanges, resultats, config)
    pannes_detail, pannes_par_engin, pannes_exclues = synthese_pannes(pannes)

    ecrire_csv(sortie / "controle.csv", resultats,
               ["date", "code_engin", "chantier", "etat", "compteur_debut", "compteur_fin", "heures_calculees", "statut", "motif"])
    ecrire_csv(sortie / "totaux_hebdo.csv", totaux, ["code_engin", "semaine", "heures_valides", "unite"])
    ecrire_csv(sortie / "vidanges.csv", vid,
               ["code_engin", "compteur_actuel", "derniere_vidange", "intervalle_h", "heures_restantes", "unite", "statut", "note"])
    ecrire_csv(sortie / "pannes_synthese.csv", pannes_detail,
               ["code_engin", "type_panne", "nb_fois", "arret_total_h"])

    n_ok = sum(1 for r in resultats if r["statut"] == "OK")
    n_flag = len(resultats) - n_ok

    print("=== CONTROLE DES POINTAGES ===")
    print(f"{len(resultats)} lignes : {n_ok} OK, {n_flag} signalees (visibles, exclues des totaux)")
    for r in resultats:
        if r["statut"] != "OK":
            print(f"  [{r['statut']}] {r['date']} {r['code_engin']} "
                  f"{r['compteur_debut']} -> {r['compteur_fin']} : {r['motif']}")

    print()
    print("=== TOTAUX HEBDOMADAIRES (lignes valides uniquement) ===")
    for t in totaux:
        print(f"  {t['code_engin']:8s} {t['semaine']} : {t['heures_valides']} {t.get('unite', 'h')}")

    print()
    print("=== VIDANGES (reglables par engin dans config.json) ===")
    for v in vid:
        print(f"  {v['code_engin']:8s} compteur {v['compteur_actuel']} {v.get('unite', 'h')} | "
              f"derniere vidange a {v['derniere_vidange']} | intervalle {v['intervalle_h']} {v.get('unite', 'h')} | "
              f"reste {v['heures_restantes']} {v.get('unite', 'h')} -> {v['statut']}")
        if v["note"]:
            print(f"           ! {v['note']}")
    for a in avert_vidanges:
        print(f"  ! {a}")

    print()
    print("=== PANNES / PROBLEMES FREQUENTS ===")
    for code in sorted(pannes_par_engin):
        s = pannes_par_engin[code]
        print(f"  {code:8s} {s['nb']} pannes, {round(s['arret_h'], 1)} h d'arret")
    print("  Detail par type :")
    for d in pannes_detail:
        print(f"    {d['code_engin']:8s} {d['type_panne']:12s} x{d['nb_fois']} ({d['arret_total_h']} h d'arret)")
    if pannes_exclues:
        print(f"  {len(pannes_exclues)} ligne(s) de panne EXCLUE(S) (non comptees) :")
        for e in pannes_exclues:
            print(f"    [EXCLUE] {e['date']} {e['code_engin']} {e['type_panne']} : {e['motif']}")

    print()
    print(f"Rapports CSV ecrits dans {sortie}/")

    from dashboard import generer_dashboard
    analyse_demo = _modele_depuis_csv(resultats, config)
    generer_dashboard(analyse_demo, sortie / "dashboard.html",
                      vidanges=vid, pannes=pannes_detail, demo=True)
    print(f"Tableau de bord de demonstration : {sortie / 'dashboard.html'}")


if __name__ == "__main__":
    main()
