# -*- coding: utf-8 -*-
"""Tests du projet. Lancer avec : python3 -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (controler_pointages, totaux_hebdo, compteur_actuel,
                  calculer_statut_vidange, suivi_vidanges, synthese_pannes)


def ligne(date, code, debut, fin):
    return {"date": date, "code_engin": code, "compteur_debut": debut,
            "compteur_fin": fin, "chantier": "CH-X"}


def panne(date, code, typ, duree):
    return {"date": date, "code_engin": code, "type_panne": typ,
            "description": "x", "duree_arret_h": duree}


class TestControle(unittest.TestCase):
    def test_calcul_simple(self):
        r = controler_pointages([ligne("2026-11-02", "EXC-101", "1240", "1248")])
        self.assertEqual(r[0]["statut"], "OK")
        self.assertEqual(r[0]["heures_calculees"], 8.0)

    def test_compteur_inverse_signale_pas_corrige(self):
        r = controler_pointages([ligne("2026-11-02", "EXC-101", "1248", "1240")])
        self.assertEqual(r[0]["statut"], "A_VERIFIER")
        self.assertEqual(r[0]["heures_calculees"], "")

    def test_lecture_manquante_jamais_zero(self):
        r = controler_pointages([ligne("2026-11-02", "EXC-101", "1240", "")])
        self.assertEqual(r[0]["statut"], "A_VERIFIER")
        self.assertNotEqual(r[0]["heures_calculees"], 0)

    def test_plus_de_24h_invalide(self):
        r = controler_pointages([ligne("2026-11-02", "EXC-101", "0", "30")])
        self.assertEqual(r[0]["statut"], "INVALIDE")

    def test_doublon_ne_gonfle_pas_le_total(self):
        rows = [ligne("2026-11-02", "EXC-101", "0", "8"),
                ligne("2026-11-02", "EXC-101", "0", "8")]
        res = controler_pointages(rows)
        self.assertEqual(res[1]["statut"], "DOUBLON")
        tot = totaux_hebdo(res)
        self.assertEqual(len(tot), 1)
        self.assertEqual(tot[0]["heures_valides"], 8.0)

    def test_ligne_signalee_exclue_du_total(self):
        rows = [ligne("2026-11-02", "EXC-101", "0", "8"),
                ligne("2026-11-03", "EXC-101", "8", "4")]
        tot = totaux_hebdo(controler_pointages(rows))
        self.assertEqual(tot[0]["heures_valides"], 8.0)


class TestVidange(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(calculer_statut_vidange(1400, 1250, 250), ("OK", 100.0))

    def test_bientot(self):
        self.assertEqual(calculer_statut_vidange(1491, 1250, 250), ("BIENTOT", 9.0))

    def test_en_retard(self):
        self.assertEqual(calculer_statut_vidange(2275.5, 2010, 250), ("EN_RETARD", -15.5))

    def test_intervalle_specifique_par_engin(self):
        self.assertEqual(calculer_statut_vidange(1050, 800, 300), ("OK", 50.0))

    def test_compteur_sous_derniere_vidange_incoherent(self):
        statut, _ = calculer_statut_vidange(1000, 1200, 250)
        self.assertEqual(statut, "A_VERIFIER")

    def test_lecture_invalide_ne_pilote_pas_la_vidange(self):
        # Derniere ligne INVALIDE (33 h/jour, compteur 921) : le statut
        # vidange doit rester base sur le dernier compteur VALIDE (888),
        # avec une note, pas un EN_RETARD calcule sur une lecture invalide.
        rows = controler_pointages([
            ligne("2026-11-06", "BUL-103", "881", "888"),
            ligne("2026-11-09", "BUL-103", "888", "921"),
        ])
        self.assertEqual(rows[1]["statut"], "INVALIDE")
        vid, _ = suivi_vidanges(
            [{"date": "2026-10-01", "code_engin": "BUL-103",
              "compteur_vidange": "800", "type_huile": "15W-40"}],
            rows, {"engins": {"BUL-103": {"intervalle_vidange_h": 300}}})
        self.assertEqual(vid[0]["compteur_actuel"], 888.0)
        self.assertEqual(vid[0]["statut"], "OK")
        self.assertIn("derniere lecture", vid[0]["note"])

    def test_vidange_compteur_non_numerique_ignoree(self):
        rows = controler_pointages([ligne("2026-11-02", "EXC-101", "0", "8")])
        vid, avert = suivi_vidanges(
            [{"date": "2026-09-15", "code_engin": "EXC-101",
              "compteur_vidange": "abc", "type_huile": "15W-40"}],
            rows, {})
        self.assertEqual(vid[0]["statut"], "A_VERIFIER")
        self.assertEqual(len(avert), 1)


class TestPannes(unittest.TestCase):
    def test_synthese_simple(self):
        detail, par_engin, exclus = synthese_pannes([
            panne("2026-11-03", "CHR-102", "Hydraulique", "3.5"),
            panne("2026-11-05", "CHR-102", "Hydraulique", "5"),
        ])
        self.assertEqual(par_engin["CHR-102"]["nb"], 2)
        self.assertEqual(detail[0]["nb_fois"], 2)
        self.assertEqual(detail[0]["arret_total_h"], 8.5)
        self.assertEqual(exclus, [])

    def test_duree_negative_exclue(self):
        detail, par_engin, exclus = synthese_pannes([
            panne("2026-11-03", "CHR-102", "Hydraulique", "-2")])
        self.assertEqual(par_engin, {})
        self.assertEqual(detail, [])
        self.assertEqual(len(exclus), 1)

    def test_duree_non_numerique_exclue(self):
        _, par_engin, exclus = synthese_pannes([
            panne("2026-11-03", "CHR-102", "Hydraulique", "?")])
        self.assertEqual(par_engin, {})
        self.assertEqual(len(exclus), 1)

    def test_doublon_panne_exclu(self):
        _, par_engin, exclus = synthese_pannes([
            panne("2026-11-03", "CHR-102", "Hydraulique", "3"),
            panne("2026-11-03", "CHR-102", "Hydraulique", "3")])
        self.assertEqual(par_engin["CHR-102"]["nb"], 1)
        self.assertEqual(len(exclus), 1)

    def test_champ_manquant_exclu(self):
        _, par_engin, exclus = synthese_pannes([
            panne("2026-11-03", "", "Hydraulique", "3")])
        self.assertEqual(par_engin, {})
        self.assertEqual(len(exclus), 1)


if __name__ == "__main__":
    unittest.main()


class TestCompteurKm(unittest.TestCase):
    def test_km_declare_pas_soumis_a_la_regle_24h(self):
        r = controler_pointages(
            [ligne("2026-11-02", "CAM-001", "45000", "45320")],
            types={"CAM-001": "km"})
        self.assertEqual(r[0]["statut"], "OK")
        self.assertEqual(r[0]["heures_calculees"], 320.0)

    def test_km_non_declare_reste_soumis_a_la_regle_24h(self):
        r = controler_pointages([ligne("2026-11-02", "CAM-001", "45000", "45320")])
        self.assertEqual(r[0]["statut"], "INVALIDE")

    def test_km_journee_tres_longue_a_confirmer(self):
        r = controler_pointages(
            [ligne("2026-11-02", "CAM-001", "45000", "45900")],
            types={"CAM-001": "km"})
        self.assertEqual(r[0]["statut"], "A_VERIFIER")
        self.assertIn("km", r[0]["motif"])

    def test_km_journee_impossible_invalide(self):
        r = controler_pointages(
            [ligne("2026-11-02", "CAM-001", "45000", "46600")],
            types={"CAM-001": "km"})
        self.assertEqual(r[0]["statut"], "INVALIDE")

    def test_hebdo_km_et_heures_jamais_melanges(self):
        res = controler_pointages([
            ligne("2026-11-02", "CAM-001", "45000", "45300"),
            ligne("2026-11-02", "EXC-101", "1200", "1208"),
        ], types={"CAM-001": "km"})
        tot = {t["code_engin"]: t for t in totaux_hebdo(res, types={"CAM-001": "km"})}
        self.assertEqual(tot["CAM-001"]["unite"], "km")
        self.assertEqual(tot["CAM-001"]["heures_valides"], 300.0)
        self.assertEqual(tot["EXC-101"]["unite"], "h")
        self.assertEqual(tot["EXC-101"]["heures_valides"], 8.0)


class TestVidangeKm(unittest.TestCase):
    def test_intervalle_km_et_seuil_bientot_km(self):
        vid, _ = suivi_vidanges(
            [{"date": "2026-10-15", "code_engin": "CAM-001", "compteur_vidange": "40000"}],
            controler_pointages(
                [ligne("2026-11-02", "CAM-001", "49300", "49700")],
                types={"CAM-001": "km"}),
            {"engins": {"CAM-001": {"type_compteur": "km"}}})
        self.assertEqual(vid[0]["unite"], "km")
        self.assertEqual(vid[0]["intervalle_h"], 10000.0)
        self.assertEqual(vid[0]["statut"], "BIENTOT")  # reste 300 km < 500

    def test_seuil_bientot_h_inchange(self):
        self.assertEqual(calculer_statut_vidange(490, 260, 250)[0], "BIENTOT")


class TestModeleDemoKmEtUnites(unittest.TestCase):
    def _modele(self, lignes, types_cfg):
        from main import _modele_depuis_csv
        cfg = {"engins": {c: {"type_compteur": t} for c, t in types_cfg.items()}}
        res = controler_pointages(lignes, types=types_cfg)
        return _modele_depuis_csv(res, cfg)

    def test_engin_km_total_km_et_prevision_km(self):
        lignes = [ligne(f"2026-11-{j:02d}", "CAM-001", str(45000 + (j - 2) * 300),
                        str(45000 + (j - 1) * 300)) for j in range(2, 8)]
        m = self._modele(lignes, {"CAM-001": "km"})
        e = m["engins"][0]
        self.assertEqual(e["type_compteur"], "km")
        self.assertEqual(e["total_km"], 1800.0)
        self.assertEqual(e["total_heures"], 0)
        self.assertEqual(e["prevision"]["unite"], "km")
        # rythme calendaire : 1800 km valides / 5 jours observes = 360 km/j
        self.assertEqual(e["prevision"]["rythme_jour"], 360.0)
        self.assertEqual(e["prevision"]["estimation"],
                         round(46800 + 360.0 * 23, 1))

    def test_sauts_repetes_unite_inconnue_exclue(self):
        # releves incompatibles avec des heures, non declares : l'engin est
        # exclu des totaux et son estimation explique pourquoi
        lignes = [ligne(f"2026-11-{j:02d}", "MSC-901", str(30000 + (j - 2) * 200),
                        str(30000 + (j - 1) * 200)) for j in range(2, 8)]
        m = self._modele(lignes, {})
        e = m["engins"][0]
        self.assertTrue(e["unite_inconnue"])
        self.assertEqual(e["total_heures"], 0)
        self.assertIn("unite du compteur a confirmer", e["prevision"]["raison"])

    def test_donnees_insuffisantes_raison_explicite(self):
        lignes = [ligne(f"2026-11-{j:02d}", "EXC-129", str(5000 + (j - 20) * 8),
                        str(5000 + (j - 19) * 8)) for j in (20, 21)]
        m = self._modele(lignes, {})
        e = m["engins"][0]
        self.assertIn("donnees insuffisantes", e["prevision"]["raison"])

    def test_affectation_reprise_du_chantier_csv(self):
        lignes = [ligne(f"2026-11-{j:02d}", "BUL-101", str(100 + (j - 2) * 8),
                        str(100 + (j - 1) * 8)) for j in range(2, 8)]
        m = self._modele(lignes, {})
        self.assertEqual(m["engins"][0]["affectation"], "CH-X")
