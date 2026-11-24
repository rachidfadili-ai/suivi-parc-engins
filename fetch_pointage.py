# -*- coding: utf-8 -*-
"""Recuperation automatique de la grille Consulter (lecture seule).

Lit l'adresse du site et les identifiants dans config.local.json, un
fichier PRIVE a la racine du projet, ignore par git et jamais commit :

    {
      "url_base": "https://example.com/Pointages",
      "utilisateur": "...",
      "mot_de_passe": "..."
    }

Le script se connecte comme le ferait le navigateur (formulaire de
connexion ASP.NET), telecharge la grille Consulter du chantier/mois
demande en lecture seule et l'enregistre en HTML local pour
pointage_import.parse_consulter_html. Il n'ecrit, ne modifie ni ne
supprime jamais rien sur le site.
"""

import http.cookiejar
import json
import urllib.parse
import urllib.request


def telecharger_consulter(config_chemin, chantier_id, annee, mois, sortie_html,
                          client=None):
    """Connecte, telecharge la grille Consulter, retourne le chemin HTML.

    Flux verifie sur le site reel : la page base + "/Auth/Login" affiche un
    formulaire qui envoie Nom + Password en POST vers "/Auth/SetLogin".
    La reponse est un JSON : {"err": true, "msg": ...} en cas d'echec,
    sinon un JSON sans err (la session est alors posee en cookie).
    """
    with open(config_chemin, encoding="utf-8") as f:
        cfg = json.load(f)
    base = cfg["url_base"].rstrip("/")

    if client is None:
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        client.addheaders = [("User-Agent", "Mozilla/5.0 (suivi-parc-engins)")]

    # 1. page de connexion : pose les cookies initiaux (aucun champ cache)
    client.open(base + "/Auth/Login", timeout=30).read()

    # 2. connexion : POST Nom + Password, reponse JSON
    corps = urllib.parse.urlencode({
        "Nom": cfg["utilisateur"],
        "Password": cfg["mot_de_passe"],
    }).encode()
    reponse = client.open(base + "/Auth/SetLogin", corps, timeout=30)
    try:
        resultat = json.loads(reponse.read().decode("utf-8", "replace"))
    except ValueError:
        raise RuntimeError("reponse de connexion inattendue (pas du JSON) : "
                           "le site a peut-etre change, utiliser --consulter "
                           "ou --excel en attendant")
    if resultat.get("err"):
        raise RuntimeError("connexion refusee : "
                           + str(resultat.get("msg", "verifier utilisateur/mot "
                                              "de passe dans config.local.json")))

    # 3. grille Consulter (GET simple, aucune ecriture)
    url_grille = ("%s/Pointages?Chantier=%s&Year=%s&Month=%s"
                  % (base, urllib.parse.quote(str(chantier_id)), annee, mois))
    html_grille = client.open(url_grille, timeout=30).read().decode("utf-8", "replace")
    if 'id="form-login"' in html_grille:
        raise RuntimeError("la grille n'a pas ete livree (retour page de connexion) : "
                           "session refusee, verifier config.local.json")

    with open(sortie_html, "w", encoding="utf-8") as f:
        f.write(html_grille)
    return sortie_html
