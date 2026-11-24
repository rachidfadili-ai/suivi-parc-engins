# -*- coding: utf-8 -*-
"""Import des pointages reels et calculs du tableau de bord.

Deux sources, meme donnee (etat + compteur par engin et par jour) :

1. La grille "Consulter" de l'application de pointage (Exploitation ->
   Pointages -> Consulter), exportee en HTML ou recuperee par
   fetch_pointage.py. Chaque cellule jour contient "ETAT(compteur)".
2. L'etat Excel "Fiche de pointage" (menu Etats -> Fiche De Pointage ->
   Exporter -> Excel). Par engin : une ligne POINTAGE (etats) et une
   ligne COMPTEUR.

Aucune URL, aucun identifiant et aucune donnee reelle n'est stocke dans
ce fichier ni dans le depot : l'utilisateur fournit le fichier telecharge
ou sa configuration privee locale (config.local.json, ignoree par git).

Regles de controle (documentees, modifiables) :
- les heures d'un jour = compteur du jour - compteur du jour precedent ;
- compteur en baisse -> INVALIDE (exclu des totaux) ;
- saut > 24 h sur un compteur horaire -> INVALIDE ;
- etat travail (1 ou 2) sans hausse du compteur -> A_VERIFIER ;
- hausse du compteur avec etat P/E/SB/F -> A_VERIFIER ;
- le 1er du mois ne peut pas etre calcule sans le compteur de fin du
  mois precedent : signale, jamais invente.
Les lignes signalees restent visibles mais exclues des totaux.
Un humain garde la decision finale : le script signale, il ne corrige
jamais la donnee d'origine.
"""

import calendar
import html.parser
import json
import re
import statistics
import zipfile
import xml.etree.ElementTree as ET

ETATS_CONNUS = {"1", "2", "P", "E", "SB", "F", "A", "D", "CP"}
ETATS_TRAVAIL = {"1", "2"}
ETATS_ARRET = {"P", "E", "SB", "F"}

SAUT_HORAIRE_MAX_H = 24.0  # compteur horaire : au-dela sur 1 jour = invalide
SAUTS_AVANT_UNITE_INCONNUE = 2  # sauts > 24 h repetes = le compteur n'est probablement pas horaire
MIN_JOURS_PREVISION = 3  # en dessous, pas d'estimation de fin de mois (donnees insuffisantes)

_NS_XLSX = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


# ---------------------------------------------------------------- Excel

def _colnum(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + ord(ch) - 64
        else:
            break
    return n


def parse_fiche_xlsx(chemin):
    """Parse l'etat Excel 'Fiche de pointage'. Retourne le dict source."""
    with zipfile.ZipFile(chemin) as z:
        noms = z.namelist()
        feuille = next(n for n in noms if re.match(r"xl/worksheets/sheet\d+\.xml", n))
        racine = ET.fromstring(z.read(feuille))

    grille = {}
    for row in racine.iter("{%s}row" % _NS_XLSX):
        rnum = row.get("r")
        for c in row:
            ref = c.get("r")
            is_el = c.find("{%s}is" % _NS_XLSX)
            if is_el is not None:
                txt = "".join(t.text or "" for t in is_el.iter("{%s}t" % _NS_XLSX))
            else:
                v = c.find("{%s}v" % _NS_XLSX)
                txt = v.text if v is not None else ""
            grille[(rnum, _colnum(ref))] = (txt or "").strip()

    entete = None
    for (r, cn), v in grille.items():
        if v.lower().replace(" ", "") == "engincode":
            entete = int(r)
            break
    if entete is None:
        raise ValueError("ligne d'entete 'Engin Code' introuvable : pas une Fiche de pointage ?")

    jours = {}
    for cn in range(1, 80):
        v = grille.get((str(entete), cn), "")
        if v.isdigit() and 1 <= int(v) <= 31:
            jours[cn] = int(v)

    chantier = ""
    for (r, cn), v in grille.items():
        if int(r) < entete and "CHANTIER" in v.upper():
            chantier = v.split(":", 1)[-1].strip()
            if chantier:
                break

    engins = []
    maxr = max(int(r) for r, _ in grille)
    r = entete + 1
    societe = ""
    while r <= maxr:
        code = grille.get((str(r), 3), "")
        pc = grille.get((str(r), 7), "").upper()
        soc = grille.get((str(r), 2), "")
        if code and soc:
            societe = soc
        if code and pc == "POINTAGE":
            etats = {d: grille.get((str(r), cn), "") for cn, d in jours.items()}
            compteurs = {}
            if grille.get((str(r + 1), 7), "").upper() == "COMPTEUR":
                compteurs = {d: grille.get((str(r + 1), cn), "") for cn, d in jours.items()}
            engins.append({
                "code": code,
                "societe": societe,
                "affectation": grille.get((str(r), 5), ""),
                "capacite": "",
                "etats": etats,
                "compteurs": compteurs,
            })
            r += 2
        else:
            r += 1
    return {"type": "excel", "chantier": chantier, "engins": engins}


# ------------------------------------------------------------ Consulter

class _GrilleConsulter(html.parser.HTMLParser):
    """Parse la grille HTML 'Consulter' (table#TableData)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dans_table = False
        self.lignes = []
        self.ligne = None
        self.cellule = None
        self.entetes = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") == "TableData":
            self.dans_table = True
        elif self.dans_table and tag == "tr":
            self.ligne = []
        elif self.dans_table and tag in ("td", "th") and self.ligne is not None:
            self.cellule = {"texte": "", "titre": a.get("title", "")}
            self.ligne.append(self.cellule)

    def handle_endtag(self, tag):
        if tag == "table" and self.dans_table:
            self.dans_table = False
        elif self.dans_table and tag == "tr" and self.ligne:
            self.lignes.append(self.ligne)
            self.ligne = None
        elif self.dans_table and tag in ("td", "th"):
            self.cellule = None

    def handle_data(self, data):
        if self.dans_table and self.cellule is not None:
            self.cellule["texte"] += data


_CELLULE_RE = re.compile(r"^\s*([A-Za-z0-9]+)\s*\(\s*([0-9.,\s]+)\s*\)\s*$")


def parse_consulter_html(chemin):
    """Parse la grille Consulter sauvegardee/recuperee en HTML."""
    with open(chemin, encoding="utf-8", errors="replace") as f:
        source = f.read()
    p = _GrilleConsulter()
    p.feed(source)

    entete = None
    corps = []
    for ligne in p.lignes:
        textes = [c["texte"].strip() for c in ligne]
        if textes and textes[0].lower() == "code":
            entete = textes
        elif entete is not None and textes and textes[0]:
            corps.append(ligne)
    if entete is None:
        raise ValueError("table Consulter (#TableData) introuvable dans le HTML")

    # colonnes jour : indices >= 3, numerotees 01, 02, ... en sequence ;
    # les colonnes de synthese (1, 2, P, E, SB, Total...) arretent la sequence
    cols_jours = {}
    attendu = 1
    for i, h in enumerate(entete):
        if i < 3:
            continue
        if h.isdigit() and int(h) == attendu:
            cols_jours[i] = attendu
            attendu += 1
        elif attendu > 1:
            break

    engins = []
    for ligne in corps:
        textes = [c["texte"].strip() for c in ligne]
        code = textes[0]
        etats, compteurs = {}, {}
        for i, jour in cols_jours.items():
            if i >= len(ligne):
                break
            txt = " ".join(ligne[i]["texte"].split())
            m = _CELLULE_RE.match(txt)
            if m:
                etats[jour] = m.group(1).upper()
                compteurs[jour] = m.group(2).replace(" ", "").replace(",", ".")
            else:
                titre = ligne[i]["titre"]
                mt = re.search(r"Compteur:\s*([0-9.,\s]+)", titre)
                me = re.search(r"Etat:\s*([^|]+)", titre)
                if me:
                    etats[jour] = _etat_depuis_libelle(me.group(1).strip())
                if mt:
                    compteurs[jour] = mt.group(1).replace(" ", "").replace(",", ".")
        engins.append({
            "code": code,
            "societe": "",
            "affectation": textes[2] if len(textes) > 2 else "",
            "capacite": textes[1] if len(textes) > 1 else "",
            "etats": etats,
            "compteurs": compteurs,
        })
    return {"type": "consulter", "chantier": "", "engins": engins}


_LIBELLES_ETAT = {
    "travail jour et nuit": "2",
    "travail jour": "1",
    "panne": "P",
    "entrep": "E",
    "stand by": "SB",
    "stand-by": "SB",
    "férié": "F",
    "ferie": "F",
    "arrivée": "A",
    "arrivee": "A",
    "départ": "D",
    "depart": "D",
    "compteur en panne": "CP",
}


def _etat_depuis_libelle(libelle):
    l = libelle.lower()
    for cle, code in _LIBELLES_ETAT.items():
        if cle in l:
            return code
    return libelle[:3].upper()


# ------------------------------------------------------------- Analyse

def _float(txt):
    try:
        return float(str(txt).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def analyser(source, config=None, annee=None, mois=None):
    """Calcule heures, anomalies et totaux a partir d'une source parsee."""
    config = config or {}
    engins_cfg = config.get("engins", {})
    resultats = []
    anomalies = []

    for e in source["engins"]:
        code = e["code"]
        cfg_e = engins_cfg.get(code, {})
        type_compteur = cfg_e.get("type_compteur", "h")
        # compteur fixe (ex. groupe toujours a 0) : l'etat travail sans hausse
        # est normal UNIQUEMENT si l'utilisateur l'a confirme dans sa config
        compteur_fixe = bool(cfg_e.get("compteur_fixe", False))
        jours_present = sorted(d for d, v in e["compteurs"].items() if v != "")
        tot_heures = 0.0
        tot_km = 0.0
        compte_etats = {}
        detail = {}
        sauts = []
        deltas_ok = []

        for jour in sorted(set(e["etats"]) | set(e["compteurs"])):
            etat = e["etats"].get(jour, "")
            cpt_txt = e["compteurs"].get(jour, "")
            cpt = _float(cpt_txt)
            statut, motifs, heures = "OK", [], None

            if etat and etat not in ETATS_CONNUS:
                statut = "A_VERIFIER"
                motifs.append(f"etat inconnu '{etat}'")
            if cpt_txt != "" and cpt is None:
                statut = "A_VERIFIER"
                motifs.append("compteur non numerique")

            precedent = None
            for d in reversed([x for x in jours_present if x < jour]):
                precedent = d
                break
            if cpt is not None and precedent is not None:
                cprev = _float(e["compteurs"][precedent])
                delta = round(cpt - cprev, 1)
                if jour - precedent > 1:
                    motifs.append(f"pas de lecture le(s) {jour - precedent - 1} jour(s) avant : "
                                  f"ecart calcule depuis le {precedent:02d}")
                if delta < 0:
                    statut = "INVALIDE"
                    motifs.append("compteur en baisse : verifier la lecture ou un changement de compteur")
                else:
                    if type_compteur == "h" and delta > SAUT_HORAIRE_MAX_H:
                        statut = "INVALIDE"
                        motifs.append(f"plus de {SAUT_HORAIRE_MAX_H:g} h entre deux lectures : invalide")
                        sauts.append({"jour": jour, "de": cprev, "vers": cpt,
                                      "saut": round(delta, 1)})
                    elif etat in ETATS_TRAVAIL and delta == 0 and not compteur_fixe:
                        statut = "A_VERIFIER"
                        motifs.append("etat travail sans hausse du compteur")
                    elif etat in ETATS_ARRET and delta > 0:
                        statut = "A_VERIFIER"
                        motifs.append(f"compteur en hausse avec etat {etat}")
                    if statut == "OK":
                        heures = delta
                        deltas_ok.append(delta)
                        if type_compteur == "h":
                            tot_heures += delta
                        else:
                            tot_km += delta
            elif cpt is not None and jour == min(jours_present or [jour]):
                motifs.append("premiere lecture du mois : heures non calculables "
                              "sans le compteur de fin du mois precedent")

            if etat:
                compte_etats[etat] = compte_etats.get(etat, 0) + 1
            detail[jour] = {"etat": etat, "compteur": cpt, "heures": heures,
                            "statut": statut, "motif": "; ".join(motifs)}
            if statut != "OK":
                anomalies.append({"engin": code, "jour": jour, "gravite": statut,
                                  "motif": "; ".join(motifs)})

        # Unite inconnue : plusieurs sauts impossibles pour un compteur
        # horaire (ex. compteur kilometrique non declare) => l'engin est
        # EXCLU des totaux d'heures tant que l'utilisateur n'a pas confirme
        # son type de compteur dans sa config privee. Jamais devine.
        unite_inconnue = False
        if type_compteur == "h":
            nb_sauts = sum(
                1 for j, d in detail.items()
                if d["compteur"] is not None and "plus de" in d["motif"])
            if nb_sauts >= SAUTS_AVANT_UNITE_INCONNUE:
                unite_inconnue = True
                tot_heures = 0.0
                for j, d in detail.items():
                    d["heures"] = None
                    if d["statut"] == "OK" and d["compteur"] is not None:
                        d["statut"] = "A_VERIFIER"
                        d["motif"] = ("unite du compteur a confirmer "
                                      "(releves incompatibles avec des heures) : "
                                      "exclu des totaux")
                        anomalies.append({"engin": code, "jour": j,
                                          "gravite": "A_VERIFIER",
                                          "motif": d["motif"]})

        # Estimation du compteur en fin de mois. Ce n'est pas une lecture :
        # une projection clairement etiquetee, ou rien si la donnee ne permet
        # pas d'estimer serieusement. Deux garde-fous :
        # - l'ancre est la DERNIERE LECTURE VALIDE (statut OK) : une lecture
        #   signalee (saut, baisse, lecture douteuse) ne sert pas de base ;
        # - le rythme est PAR JOUR CALENDAIRE : heures valides / jours
        #   observes entre la premiere et la derniere lecture, pour ne pas
        #   surestimer une machine qui ne travaille pas tous les jours.
        prevision = None
        if annee and mois and jours_present:
            jours_valides = [j for j in jours_present
                             if detail[j]["statut"] == "OK"]
            j_dernier = max(jours_valides) if jours_valides else None
            j_premier = min(jours_present)
            if unite_inconnue:
                prevision = {"raison": "unite du compteur a confirmer : "
                                       "pas d'estimation"}
            elif j_dernier is None:
                prevision = {"raison": "aucune lecture valide ce mois : "
                                       "pas d'estimation"}
            else:
                jours_restants = calendar.monthrange(annee, mois)[1] - j_dernier
                jours_observe = j_dernier - j_premier
                if jours_restants <= 0:
                    prevision = None  # mois termine, rien a estimer
                elif len(deltas_ok) < MIN_JOURS_PREVISION or jours_observe < 1:
                    prevision = {"raison": "donnees insuffisantes "
                                           "(%d jour(s) valide(s)) : pas d'estimation"
                                           % len(deltas_ok)}
                else:
                    heures_valides = sum(deltas_ok)
                    rythme = heures_valides / jours_observe
                    prevision = {
                        "dernier_compteur": _float(e["compteurs"][j_dernier]),
                        "dernier_jour": j_dernier,
                        "rythme_jour": round(rythme, 1),
                        "heures_base": round(heures_valides, 1),
                        "jours_base": len(deltas_ok),
                        "jours_observe": jours_observe,
                        "jours_restants": jours_restants,
                        "estimation": round(_float(e["compteurs"][j_dernier])
                                            + rythme * jours_restants, 1),
                        "unite": type_compteur,
                    }

        resultats.append({
            "code": code,
            "societe": e["societe"],
            "affectation": e["affectation"],
            "capacite": e["capacite"],
            "type_compteur": type_compteur,
            "unite_inconnue": unite_inconnue,
            "jours": detail,
            "total_heures": round(tot_heures, 1),
            "total_km": round(tot_km, 1),
            "compte_etats": compte_etats,
            "sauts": sauts,
            "prevision": prevision,
            "derniere_lecture": (max(jours_present) if jours_present else None),
        })

    return {
        "source": source["type"],
        "chantier": source.get("chantier", ""),
        "annee": annee,
        "mois": mois,
        "engins": resultats,
        "anomalies": sorted(anomalies, key=lambda a: (a["engin"], a["jour"])),
    }


def synthese(analyse):
    """Petits indicateurs globaux pour l'en-tete du tableau de bord."""
    engins = analyse["engins"]
    total_h = round(sum(e["total_heures"] for e in engins), 1)
    etats = {}
    for e in engins:
        for k, v in e["compte_etats"].items():
            etats[k] = etats.get(k, 0) + v
    return {
        "nb_engins": len(engins),
        "heures_totales": total_h,
        "nb_anomalies": len(analyse["anomalies"]),
        "nb_pannes_jours": etats.get("P", 0),
        "repartition_etats": etats,
        "engins_unite_inconnue": [e["code"] for e in engins if e.get("unite_inconnue")],
    }


def exporter_json(analyse, chemin):
    """Donnees calculees en JSON, alimente le tableau de bord."""
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(analyse, f, ensure_ascii=False, indent=1)
