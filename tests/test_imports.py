# -*- coding: utf-8 -*-
"""Tests des imports reels (Excel Fiche de pointage + grille Consulter HTML)
et des regles d'analyse. Les fixtures sont fabriquees ici : aucune donnee
reelle n'est embarquee dans le depot."""

import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pointage_import as si


def _xlsx_minimal():
    """Fabrique un petit xlsx qui imite la structure reelle de l'etat."""
    def ligne(r, cellules):
        cs = ""
        for ref, val, num in cellules:
            if num:
                cs += f'<c r="{ref}"><v>{val}</v></c>'
            else:
                cs += (f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>')
        return f'<row r="{r}">{cs}</row>'

    lignes = [
        ligne(2, [("B2", "CHANTIER: PARC TEST", False)]),
        ligne(4, [("B4", "Sociéte", False), ("C4", "Engin Code", False),
                  ("E4", "Affectation", False), ("G4", "P / C", False)]
                 + [(f"{chr(72+i)}4", str(i + 1), True) for i in range(4)]),
        ligne(5, [("B5", "SOM", False), ("C5", "AAA-1", False),
                  ("E5", "CHANTIER", False), ("G5", "POINTAGE", False),
                  ("H5", "1", False), ("I5", "1", False), ("J5", "P", False), ("K5", "2", False)]),
        ligne(6, [("G6", "COMPTEUR", False), ("H6", "100", True), ("I6", "108", True),
                  ("J6", "108", True), ("K6", "140", True)]),
        ligne(7, [("C7", "BBB-2", False), ("E7", "DIVERS", False), ("G7", "POINTAGE", False),
                  ("H7", "1", False), ("I7", "1", False), ("J7", "1", False), ("K7", "1", False)]),
        ligne(8, [("G8", "COMPTEUR", False), ("H8", "500", True), ("I8", "495", True),
                  ("J8", "520", True), ("K8", "528", True)]),
    ]
    sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData>' + "".join(lignes) + "</sheetData></worksheet>")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return tampon.getvalue()


HTML_GRILLE = """
<table id="TableData"><thead><tr>
<th>Code</th><th>Capacite</th><th>Affectation</th>
<th class="gp-day">01</th><th class="gp-day">02</th><th class="gp-day">03</th>
<th>1</th><th>2</th><th>P</th><th>Total</th>
</tr></thead><tbody>
<tr><th>AAA-1</th><th>3m3</th><th>CHANTIER</th>
<td><a title="Etat: Travail jour | Compteur: 100">1<text>(100)</text></a></td>
<td><a title="Etat: Travail jour | Compteur: 108">1<text>(108)</text></a></td>
<td><a title="Etat: Panne | Compteur: 108">P<text>(108)</text></a></td>
<td>2</td><td>0</td><td>1</td><td>3</td></tr>
<tr><th>BBB-2</th><th></th><th>DIVERS</th>
<td><a title="Etat: Travail jour | Compteur: 500">1<text>(500)</text></a></td>
<td><a title="Etat: Férié | Compteur: 500">F<text>(500)</text></a></td>
<td></td>
<td>1</td><td>0</td><td>0</td><td>1</td></tr>
</tbody></table>
"""


class TestFicheXlsx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        self.tmp.write(_xlsx_minimal())
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_parse_structure(self):
        src = si.parse_fiche_xlsx(self.tmp.name)
        self.assertEqual(src["type"], "excel")
        self.assertIn("PARC TEST", src["chantier"])
        self.assertEqual(len(src["engins"]), 2)
        a, b = src["engins"]
        self.assertEqual(a["code"], "AAA-1")
        self.assertEqual(a["societe"], "SOM")
        self.assertEqual(a["etats"][3], "P")
        self.assertEqual(a["compteurs"][1], "100")
        self.assertEqual(b["code"], "BBB-2")
        self.assertEqual(b["societe"], "SOM")  # fusion : heritee de la ligne precedente

    def test_analyse_regles(self):
        src = si.parse_fiche_xlsx(self.tmp.name)
        ana = si.analyser(src, annee=2026, mois=1)
        a, b = ana["engins"]
        # AAA-1 : j1 premiere lecture (pas d'heures), j2 = +8 OK, j3 P stable OK(0 h? non: pas de calcul travail),
        # j4 etat 2 +32 h > 24 -> INVALIDE
        self.assertIsNone(a["jours"][1]["heures"])
        self.assertEqual(a["jours"][2]["heures"], 8)
        self.assertEqual(a["jours"][4]["statut"], "INVALIDE")
        # BBB-2 : j2 compteur en baisse -> INVALIDE, j3 hausse +25 > 24 -> INVALIDE, j4 +8 OK
        self.assertEqual(b["jours"][2]["statut"], "INVALIDE")
        self.assertEqual(b["jours"][3]["statut"], "INVALIDE")
        self.assertEqual(b["jours"][4]["heures"], 8)
        # les totaux excluent les invalides
        self.assertEqual(b["total_heures"], 8)
        self.assertTrue(any(x["gravite"] == "INVALIDE" for x in ana["anomalies"]))

    def test_etat_travail_sans_hausse(self):
        src = si.parse_fiche_xlsx(self.tmp.name)
        src["engins"][0]["etats"][2] = "1"
        src["engins"][0]["compteurs"][2] = "100"  # meme compteur que j1
        ana = si.analyser(src, annee=2026, mois=1)
        self.assertEqual(ana["engins"][0]["jours"][2]["statut"], "A_VERIFIER")


class TestConsulterHtml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
        self.tmp.write(HTML_GRILLE)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_parse_grille(self):
        src = si.parse_consulter_html(self.tmp.name)
        self.assertEqual(src["type"], "consulter")
        self.assertEqual(len(src["engins"]), 2)
        a, b = src["engins"]
        self.assertEqual(a["code"], "AAA-1")
        self.assertEqual(a["capacite"], "3m3")
        self.assertEqual(a["etats"][1], "1")
        self.assertEqual(a["etats"][3], "P")
        self.assertEqual(a["compteurs"][2], "108")
        self.assertEqual(b["etats"][2], "F")
        self.assertNotIn(3, b["etats"])  # cellule vide = pas de pointage
        # les colonnes de synthese (1, 2, P, Total) ne doivent pas passer pour des jours
        self.assertEqual(max(a["etats"]), 3)

    def test_analyse_consulter(self):
        src = si.parse_consulter_html(self.tmp.name)
        ana = si.analyser(src, annee=2026, mois=11)
        a, b = ana["engins"]
        self.assertEqual(a["jours"][2]["heures"], 8)
        self.assertEqual(a["jours"][3]["statut"], "OK")  # P sans hausse : coherent
        self.assertEqual(b["compte_etats"]["F"], 1)


class TestDashboard(unittest.TestCase):
    def test_generation_html(self):
        from dashboard import generer_dashboard
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.write(_xlsx_minimal())
        tmp.close()
        src = si.parse_fiche_xlsx(tmp.name)
        os.unlink(tmp.name)
        ana = si.analyser(src, annee=2026, mois=1)
        sortie = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        sortie.close()
        generer_dashboard(ana, sortie.name, demo=True)
        with open(sortie.name, encoding="utf-8") as f:
            page = f.read()
        os.unlink(sortie.name)
        self.assertIn("AAA-1", page)
        self.assertIn("Suivi de parc engins", page)
        self.assertNotIn("__DONNEES__", page)  # gabarit entierement rempli


if __name__ == "__main__":
    unittest.main()


class _FausseReponse:
    def __init__(self, corps, url=""):
        self._corps = corps.encode("utf-8")
        self._url = url

    def read(self):
        return self._corps

    def geturl(self):
        return self._url


class _FauxClient:
    """Simule le site : login JSON puis grille Consulter."""

    def __init__(self, login_json, grille_html):
        self.login_json = login_json
        self.grille_html = grille_html
        self.posts = []

    def open(self, url, data=None, timeout=30):
        if data is not None:
            self.posts.append((url, data.decode("utf-8")))
            return _FausseReponse(self.login_json)
        return _FausseReponse(self.grille_html)


class TestFetch(unittest.TestCase):
    import tempfile, os

    def _config(self, dossier):
        import json
        p = self.os.path.join(dossier, "config.local.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"url_base": "https://example.com/Pointages",
                       "utilisateur": "u", "mot_de_passe": "p"}, f)
        return p

    def test_flux_nom_password_setlogin(self):
        import json
        from fetch_pointage import telecharger_consulter
        with self.tempfile.TemporaryDirectory() as d:
            client = _FauxClient('{"err": false, "url": "/Pointages"}',
                                 "<html>grille</html>")
            sortie = self.os.path.join(d, "grille.html")
            telecharger_consulter(self._config(d), 1234, 2026, 11, sortie,
                                  client=client)
            url_post, corps = client.posts[0]
            self.assertTrue(url_post.endswith("/Auth/SetLogin"))
            self.assertIn("Nom=u", corps)
            self.assertIn("Password=p", corps)
            self.assertEqual(open(sortie, encoding="utf-8").read(),
                             "<html>grille</html>")

    def test_login_refuse_leve_erreur(self):
        from fetch_pointage import telecharger_consulter
        with self.tempfile.TemporaryDirectory() as d:
            client = _FauxClient(
                '{"err": true, "msg": "Nom d\\u0027utilisateur ou mot de passe incorrect."}',
                "<html>grille</html>")
            with self.assertRaises(RuntimeError):
                telecharger_consulter(self._config(d), 1234, 2026, 11,
                                      self.os.path.join(d, "g.html"), client=client)

    def test_retour_page_login_detecte(self):
        from fetch_pointage import telecharger_consulter
        with self.tempfile.TemporaryDirectory() as d:
            client = _FauxClient('{"err": false}',
                                 '<form id="form-login"></form>')
            with self.assertRaises(RuntimeError):
                telecharger_consulter(self._config(d), 1234, 2026, 11,
                                      self.os.path.join(d, "g.html"), client=client)


class TestUniteInconnue(unittest.TestCase):
    def _source(self, compteurs):
        return {"type": "consulter", "chantier": "X", "engins": [{
            "code": "TOY1", "societe": "", "affectation": "", "capacite": "",
            "etats": {j: "1" for j in compteurs},
            "compteurs": compteurs,
        }]}

    def test_releves_km_exclus_des_heures(self):
        import pointage_import as si
        # compteur kilometrique non declare : sauts > 24 repetes
        src = self._source({1: 100.0, 2: 250.0, 3: 400.0, 4: 410.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        e = a["engins"][0]
        self.assertTrue(e["unite_inconnue"])
        self.assertEqual(e["total_heures"], 0.0)
        self.assertIsNone(e["jours"][4]["heures"])
        self.assertEqual(e["jours"][4]["statut"], "A_VERIFIER")
        s = si.synthese(a)
        self.assertEqual(s["heures_totales"], 0.0)
        self.assertEqual(s["engins_unite_inconnue"], ["TOY1"])

    def test_un_seul_saut_reste_une_erreur_de_lecture(self):
        import pointage_import as si
        # un seul saut > 24 : ligne invalide, engin PAS exclu
        src = self._source({1: 100.0, 2: 108.0, 3: 200.0, 4: 208.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        e = a["engins"][0]
        self.assertFalse(e["unite_inconnue"])
        self.assertEqual(e["total_heures"], 16.0)
        self.assertEqual(e["jours"][3]["statut"], "INVALIDE")

    def test_config_km_confirmee_compte_en_km(self):
        import pointage_import as si
        src = self._source({1: 100.0, 2: 250.0, 3: 400.0})
        a = si.analyser(src, {"engins": {"TOY1": {"type_compteur": "km"}}},
                        annee=2026, mois=11)
        e = a["engins"][0]
        self.assertFalse(e["unite_inconnue"])
        self.assertEqual(e["total_km"], 300.0)


class TestSautsEtPrevision(unittest.TestCase):
    def _source(self, compteurs, code="ENG1"):
        return {"type": "consulter", "chantier": "X", "engins": [{
            "code": code, "societe": "", "affectation": "", "capacite": "",
            "etats": {j: "1" for j in compteurs},
            "compteurs": compteurs,
        }]}

    def test_saut_enregistre_avec_releves(self):
        import pointage_import as si
        src = self._source({1: 100.0, 2: 108.0, 3: 200.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        s = a["engins"][0]["sauts"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["jour"], 3)
        self.assertEqual(s[0]["de"], 108.0)
        self.assertEqual(s[0]["vers"], 200.0)
        self.assertEqual(s[0]["saut"], 92.0)

    def test_prevision_rythme_calendaire_jours_valides(self):
        import pointage_import as si
        # 5 jours valides a 7 h, un jour invalide : exclu du numerateur
        # mais ses jours calendaires restent au denominateur
        src = self._source({1: 800.0, 2: 807.0, 3: 814.0, 4: 821.0, 5: 828.0,
                            6: 900.0, 7: 907.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        p = a["engins"][0]["prevision"]
        self.assertEqual(p["heures_base"], 35.0)      # 5 x 7 h valides
        self.assertEqual(p["jours_observe"], 6)       # jour 1 -> jour 7
        self.assertAlmostEqual(p["rythme_jour"], round(35.0 / 6, 1), places=1)
        self.assertEqual(p["dernier_compteur"], 907.0)
        self.assertEqual(p["jours_restants"], 30 - 7)
        self.assertAlmostEqual(p["estimation"], round(907.0 + (35.0 / 6) * 23, 1),
                               places=1)
        self.assertEqual(p["jours_base"], 5)

    def test_prevision_ancre_sur_derniere_lecture_valide(self):
        import pointage_import as si
        # le dernier releve (jour 5) est un saut invalide : l'ancre doit
        # reculer a la derniere lecture valide (jour 4)
        src = self._source({1: 100.0, 2: 108.0, 3: 116.0, 4: 124.0, 5: 200.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        p = a["engins"][0]["prevision"]
        self.assertEqual(p["dernier_jour"], 4)
        self.assertEqual(p["dernier_compteur"], 124.0)
        self.assertEqual(p["rythme_jour"], 8.0)
        self.assertEqual(p["jours_restants"], 26)
        self.assertAlmostEqual(p["estimation"], 124.0 + 8.0 * 26, places=1)

    def test_pas_de_prevision_si_donnees_insuffisantes(self):
        import pointage_import as si
        src = self._source({1: 100.0, 2: 108.0})  # 1 seul delta valide
        a = si.analyser(src, {}, annee=2026, mois=11)
        p = a["engins"][0]["prevision"]
        self.assertIn("insuffisantes", p["raison"])
        self.assertNotIn("estimation", p)

    def test_pas_de_prevision_si_unite_inconnue(self):
        import pointage_import as si
        src = self._source({1: 100.0, 2: 250.0, 3: 400.0, 4: 550.0})
        a = si.analyser(src, {}, annee=2026, mois=11)
        p = a["engins"][0]["prevision"]
        self.assertIn("unite", p["raison"])
        self.assertNotIn("estimation", p)

    def test_prevision_km_si_confirme(self):
        import pointage_import as si
        src = self._source({1: 1000.0, 2: 1150.0, 3: 1300.0, 4: 1450.0})
        a = si.analyser(src, {"engins": {"ENG1": {"type_compteur": "km"}}},
                        annee=2026, mois=11)
        p = a["engins"][0]["prevision"]
        self.assertEqual(p["unite"], "km")
        self.assertAlmostEqual(p["estimation"], 1450.0 + 150.0 * 26, places=1)
