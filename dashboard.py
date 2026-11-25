# -*- coding: utf-8 -*-
"""Genere le tableau de bord : une page HTML autonome.

Aucune bibliotheque externe, aucun CDN : la page fonctionne hors ligne
et peut s'ouvrir dans n'importe quel navigateur. Les donnees calculees
sont embarquees en JSON dans la page ; les graphiques sont dessines en
SVG par le script embarque.

Le script signale les anomalies, il ne corrige jamais la donnee
d'origine : les lignes INVALIDE ou A_VERIFIER restent visibles dans la
grille et sont exclues des totaux.
"""

import json

_MOIS = ["", "janvier", "fevrier", "mars", "avril", "mai", "juin",
         "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]


def _modele(analyse, vidanges=None, pannes=None, demo=False):
    s_engins = []
    for e in analyse["engins"]:
        jours = []
        for j in sorted(e["jours"]):
            d = e["jours"][j]
            jours.append({
                "j": j, "etat": d["etat"], "cpt": d["compteur"],
                "h": d["heures"], "st": d["statut"], "motif": d["motif"],
            })
        s_engins.append({
            "code": e["code"], "societe": e["societe"],
            "affectation": e["affectation"], "capacite": e["capacite"],
            "type": e["type_compteur"], "jours": jours,
            "uniteInconnue": bool(e.get("unite_inconnue")),
            "totalH": e["total_heures"], "totalKm": e.get("total_km", 0), "etats": e["compte_etats"],
            "sauts": e.get("sauts", []), "prev": e.get("prevision"),
            "dernier": e["derniere_lecture"],
        })
    return {
        "chantier": analyse.get("chantier", ""),
        "periode": ("%s %s" % (_MOIS[analyse["mois"]], analyse["annee"])
                    if analyse.get("mois") and analyse.get("annee") else ""),
        "source": analyse.get("source", ""),
        "demo": bool(demo),
        "engins": s_engins,
        "anomalies": analyse.get("anomalies", []),
        "vidanges": vidanges,
        "pannes": pannes,
    }


def generer_dashboard(analyse, chemin_sortie, vidanges=None, pannes=None, demo=False):
    from pointage_import import synthese
    modele = _modele(analyse, vidanges, pannes, demo)
    kpis = synthese(analyse)
    donnees = json.dumps({"m": modele, "k": kpis}, ensure_ascii=False)
    page = _GABARIT.replace("__DONNEES__", donnees)
    with open(chemin_sortie, "w", encoding="utf-8") as f:
        f.write(page)
    return chemin_sortie


_GABARIT = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Suivi de parc engins - Tableau de bord</title>
<style>
:root{--fond:#0e1424;--carte:#17203a;--encre:#e8edf7;--doux:#9aa7c2;--ligne:#263156;
--accent:#4f8cff;--ok:#22c55e;--info:#38bdf8;--warn:#f59e0b;--bad:#ef4444;--sb:#38bdf8;--e:#facc15;--f:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",system-ui,-apple-system,sans-serif;background:var(--fond);color:var(--encre);padding:18px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;margin-bottom:14px}
h1{font-size:20px}
.sous{color:var(--doux);font-size:13px}
.badge-demo{background:#fef3c7;color:#92400e;border:1px solid #fcd34d;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.carte{background:var(--carte);border:1px solid var(--ligne);border-radius:10px;padding:12px 14px}
.carte .v{font-size:22px;font-weight:700}
.carte .l{font-size:12px;color:var(--doux);margin-top:2px}
.section{background:var(--carte);border:1px solid var(--ligne);border-radius:10px;padding:14px;margin-bottom:16px;overflow-x:auto}
h2{font-size:15px;margin-bottom:10px}
table{border-collapse:collapse;font-size:12px}
th,td{border:1px solid var(--ligne);padding:3px 5px;text-align:center;white-space:nowrap}
thead th{background:#eef2f9;font-weight:600}
.codecol{text-align:left;font-weight:600;position:sticky;left:0;background:var(--carte)}
.cell{width:26px;height:26px;border-radius:5px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#fff;cursor:default}
.e1{background:var(--ok)}.e2{background:var(--info)}.eP{background:var(--bad)}.eE{background:var(--e)}
.eSB{background:var(--sb)}.eF{background:var(--f)}.eA{background:#8b5cf6}.eD{background:#6d28d9}.eCP{background:#111827}
.ev{background:#f1f5f9;color:#cbd5e1}
.flague{outline:2px solid var(--warn);outline-offset:-2px}
.invalide{outline:2px solid var(--bad);outline-offset:-2px;text-decoration:line-through}
.legende{display:flex;flex-wrap:wrap;gap:8px;font-size:11px;color:var(--doux);margin:6px 0 10px}
.legende span{display:inline-flex;align-items:center;gap:4px}
.pastille{width:12px;height:12px;border-radius:3px;display:inline-block}
select{padding:5px 8px;border:1px solid var(--ligne);border-radius:6px;font-size:13px;background:#fff}
.ligne-anomalie td{text-align:left}
.gA_VERIFIER{color:var(--warn);font-weight:600}
.gINVALIDE{color:var(--bad);font-weight:600}
.note{font-size:12px;color:var(--doux);margin-top:8px}
.graphwrap{display:flex;gap:6px;margin-top:8px}
.axey{display:flex;flex-direction:column;justify-content:space-between;font-size:10px;color:var(--doux);text-align:right;padding-bottom:18px}
.barscol{flex:1}
.bars{display:flex;align-items:flex-end;gap:3px;height:150px;border-left:1px solid var(--ligne);border-bottom:1px solid var(--ligne);padding-left:4px}
.bar{flex:1;background:var(--accent);border-radius:3px 3px 0 0;min-width:6px;position:relative;cursor:pointer}
.bar:hover,.bar.actif{background:#1d4ed8}
.bar .tip{display:none;position:absolute;bottom:105%;left:50%;transform:translateX(-50%);background:#111827;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;white-space:nowrap;z-index:2}
.bar:hover .tip,.bar.actif .tip{display:block}
.bar .val{position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:10px;color:var(--doux)}
.axesx{display:flex;gap:3px;padding-left:4px}
.axesx span{flex:1;min-width:6px;text-align:center;font-size:10px;color:var(--doux)}
.rep{display:flex;height:16px;border-radius:6px;overflow:hidden;margin-top:6px}
.rep div{height:100%}
.filtres{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.filtres input{padding:5px 8px;border:1px solid var(--ligne);border-radius:6px;font-size:13px;min-width:200px}
.compte{font-size:12px;color:var(--doux)}
.pager{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--doux)}
.pager button{padding:3px 10px;border:1px solid var(--ligne);border-radius:6px;background:#fff;cursor:pointer;font-size:12px}
.pager button:disabled{opacity:.4;cursor:default}

/* theme sombre + bandeau engins (SVG embarque, aucun fichier externe) */
body{padding:0}
body::before{content:"";display:block;height:210px;
background:linear-gradient(180deg,#1b2a52 0%,#27408b 55%,#3b5bb5 100%)}
header,.cartes,.section,.note,footer{margin-left:22px;margin-right:22px}
header{margin-top:-190px;position:relative;z-index:2;
background:url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNjAwIiBoZWlnaHQ9IjIyMCIgdmlld0JveD0iMCAwIDE2MDAgMjIwIj4KPGcgZmlsbD0iIzBiMTIyNiI+CjxyZWN0IHg9IjAiIHk9IjE5MCIgd2lkdGg9IjE2MDAiIGhlaWdodD0iMzAiLz4KPGc+CjxyZWN0IHg9IjYwIiB5PSIxMjAiIHdpZHRoPSIxNTAiIGhlaWdodD0iNTUiIHJ4PSI2Ii8+CjxwYXRoIGQ9Ik0yMTAgMTc1IHYtNzAgaDU1IGwzNSAzNSB2MzUgeiIvPgo8cmVjdCB4PSIyMjUiIHk9IjExNSIgd2lkdGg9IjI4IiBoZWlnaHQ9IjIyIiByeD0iMyIgZmlsbD0iIzBiMTIyNiIvPgo8Y2lyY2xlIGN4PSI5NSIgY3k9IjE4NSIgcj0iMjIiLz48Y2lyY2xlIGN4PSIxODUiIGN5PSIxODUiIHI9IjIyIi8+PGNpcmNsZSBjeD0iMjQ1IiBjeT0iMTg1IiByPSIyMiIvPgo8Y2lyY2xlIGN4PSI5NSIgY3k9IjE4NSIgcj0iOSIgZmlsbD0iIzFjMmE0YSIvPjxjaXJjbGUgY3g9IjE4NSIgY3k9IjE4NSIgcj0iOSIgZmlsbD0iIzFjMmE0YSIvPjxjaXJjbGUgY3g9IjI0NSIgY3k9IjE4NSIgcj0iOSIgZmlsbD0iIzFjMmE0YSIvPgo8cGF0aCBkPSJNNjAgMTIwIGgxNTAgbC0xMiAtMjggaC0xMjYgeiIvPgo8L2c+CjxnPgo8cmVjdCB4PSI0MzAiIHk9IjE1MCIgd2lkdGg9IjEyMCIgaGVpZ2h0PSIzMiIgcng9IjE0Ii8+CjxyZWN0IHg9IjQ1NSIgeT0iMTEyIiB3aWR0aD0iNjAiIGhlaWdodD0iNDIiIHJ4PSI2Ii8+CjxwYXRoIGQ9Ik01MTUgMTMwIEw2MDAgODggTDY0MCA5NiBMNTYwIDE0MCBaIi8+CjxwYXRoIGQ9Ik02MDAgODggTDY2OCAxMzAgTDY2MCAxNDIgTDYzMiAxMDAgWiIvPgo8cGF0aCBkPSJNNjYwIDE0MiBxMTggMTAgNiAyNiBsLTI0IDQgcTE0IC0xNiA2IC0zMCB6Ii8+CjxjaXJjbGUgY3g9IjQ3MCIgY3k9IjE4NiIgcj0iMTYiLz48Y2lyY2xlIGN4PSI1MTUiIGN5PSIxODYiIHI9IjE2Ii8+CjwvZz4KPGc+CjxyZWN0IHg9Ijc2MCIgeT0iNjAiIHdpZHRoPSIxNCIgaGVpZ2h0PSIxMzAiLz4KPHBhdGggZD0iTTc2NyAzMCBMOTgwIDg0IEw5NzUgOTIgTDc2NyA0OCBaIi8+CjxwYXRoIGQ9Ik03NjcgMzAgTDcxMiA3OCBMNzIwIDg2IEw3NjcgNDggWiIvPgo8cmVjdCB4PSI3MDAiIHk9Ijc4IiB3aWR0aD0iMjIiIGhlaWdodD0iMTYiLz4KPGxpbmUgeDE9Ijk1MCIgeTE9Ijg2IiB4Mj0iOTUwIiB5Mj0iMTUwIiBzdHJva2U9IiMwYjEyMjYiIHN0cm9rZS13aWR0aD0iNSIvPgo8cmVjdCB4PSI5MzgiIHk9IjE1MCIgd2lkdGg9IjI0IiBoZWlnaHQ9IjE4IiByeD0iMyIvPgo8cmVjdCB4PSI3NDIiIHk9IjE5MCIgd2lkdGg9IjUwIiBoZWlnaHQ9IjEwIi8+CjwvZz4KPGcgb3BhY2l0eT0iMC44NSI+CjxyZWN0IHg9IjEwNTAiIHk9IjE0MCIgd2lkdGg9IjEyMCIgaGVpZ2h0PSI0NCIgcng9IjUiLz4KPHBhdGggZD0iTTExNzAgMTg0IHYtNTYgaDQ0IGwyOCAyOCB2MjggeiIvPgo8Y2lyY2xlIGN4PSIxMDgwIiBjeT0iMTkyIiByPSIxNyIvPjxjaXJjbGUgY3g9IjExNTAiIGN5PSIxOTIiIHI9IjE3Ii8+PGNpcmNsZSBjeD0iMTIxOCIgY3k9IjE5MiIgcj0iMTciLz4KPHBhdGggZD0iTTEwNTAgMTQwIGgxMjAgbC0xMCAtMjIgaC0xMDAgeiIvPgo8L2c+CjxnPgo8cmVjdCB4PSIxMzMwIiB5PSIxNTAiIHdpZHRoPSI5MCIgaGVpZ2h0PSIzNCIgcng9IjgiLz4KPHJlY3QgeD0iMTM2MCIgeT0iMTE4IiB3aWR0aD0iNDAiIGhlaWdodD0iMzYiIHJ4PSI1Ii8+CjxwYXRoIGQ9Ik0xMzMwIDE2MCBMMTI3MCAxNTAgTDEyNjYgMTY4IEwxMzMwIDE3NiBaIi8+CjxwYXRoIGQ9Ik0xMjcwIDE1MCBxLTIyIDQgLTE4IDI4IGwyMCAyIHEtNiAtMTYgNiAtMjQgeiIvPgo8Y2lyY2xlIGN4PSIxMzUyIiBjeT0iMTkwIiByPSIxOCIvPjxjaXJjbGUgY3g9IjE0MDgiIGN5PSIxOTAiIHI9IjE4Ii8+CjxjaXJjbGUgY3g9IjEzNTIiIGN5PSIxOTAiIHI9IjciIGZpbGw9IiMxYzJhNGEiLz48Y2lyY2xlIGN4PSIxNDA4IiBjeT0iMTkwIiByPSI3IiBmaWxsPSIjMWMyYTRhIi8+CjwvZz4KPC9nPgo8L3N2Zz4=) bottom center/cover no-repeat;
border-radius:14px;padding:26px 24px 20px;color:#fff;
box-shadow:0 8px 30px rgba(2,6,23,.45)}
h1{font-size:26px;letter-spacing:.3px;text-shadow:0 2px 8px rgba(2,6,23,.6)}
header .sous{color:#cdd8f0}
.badge-demo{background:rgba(250,204,21,.18);color:#fde68a;border-color:#f59e0b}
.carte,.section{background:rgba(23,32,58,.92);box-shadow:0 4px 18px rgba(2,6,23,.35)}
.carte .v{color:#fff}
h2{color:#fff}
thead th{background:#1f2a4a;color:#dbe4f5}
th,td{border-color:#263156}
.codecol{background:#1a2440;color:#e8edf7}
.ev{background:#232f52;color:#41508a}
select,.filtres input{background:#0e1424;color:#e8edf7;border-color:#31406b}
.pager button{background:#0e1424;color:#e8edf7;border-color:#31406b}
.bar:hover,.bar.actif{background:#2f6bff}
.bars{border-color:#31406b}
</style>
</head>
<body>
<header>
  <h1>Suivi de parc engins</h1>
  <span class="sous" id="periode"></span>
  <span class="badge-demo" id="demo" style="display:none">JEU DE DONNEES GENERE</span>
  <div class="note">Projet personnel de Rachid Fadili (rachidfadili2002@outlook.com) - concu a partir de son experience terrain dans le suivi d'engins de chantier.</div>
</header>
<div class="cartes" id="kpis"></div>

<div class="section">
  <h2>Grille des etats journaliers</h2>
  <div class="legende">
    <span><i class="pastille e1"></i>1 poste</span>
    <span><i class="pastille e2"></i>2 postes</span>
    <span><i class="pastille eP"></i>Panne</span>
    <span><i class="pastille eE"></i>Entrepose</span>
    <span><i class="pastille eSB"></i>Stand-by</span>
    <span><i class="pastille eF"></i>Ferie</span>
    <span><i class="pastille eCP"></i>Compteur en panne</span>
    <span>cadre orange = a verifier, rouge barre = invalide (exclus des totaux)</span>
  </div>
  <div class="filtres" id="filtres" style="display:none">
    <input id="fCode" type="search" placeholder="Rechercher un engin (code)...">
    <select id="fType"><option value="">Tous compteurs</option><option value="h">Compteurs horaires</option><option value="km">Compteurs kilometres</option><option value="inc">Unite a confirmer</option></select>
    <select id="fChantier"><option value="">Tous chantiers</option></select>
    <select id="fAlerte"><option value="">Tous</option><option value="sig">Avec signalements</option><option value="saut">Avec sauts de compteur</option><option value="noprev">Sans estimation fiable</option></select>
    <span class="compte" id="fCompte"></span>
  </div>
  <div id="grille"></div>
  <div class="note">Survoler une cellule : compteur, heures calculees et motif de signalement. Les heures = compteur du jour - compteur du jour precedent.</div>
</div>

<div class="section">
  <h2>Heures par jour</h2>
  <select id="choix"></select>
  <div class="graphwrap">
    <div class="axey" id="axey"></div>
    <div class="barscol">
      <div class="bars" id="bars"></div>
      <div class="axesx" id="axesx"></div>
    </div>
  </div>
  <div class="note" id="totEngin"></div>
</div>

<div class="section">
  <h2>Repartition des etats par engin</h2>
  <div id="repartition"></div>
</div>

<div class="section" id="secPrev" style="display:none">
  <h2>Sauts de compteur et estimation de fin de mois</h2>
  <div id="sauts"></div>
  <div id="previsions"></div>
  <div class="note">L'estimation est une PROJECTION au rythme constate (heures valides / jours calendaires observes, jours signales exclus du numerateur), ancree sur la derniere lecture VALIDE : ce n'est pas une lecture, elle sert a anticiper sans aucune garantie d'exactitude. Sans assez de jours valides ou si l'unite du compteur est a confirmer, aucune estimation n'est affichee.</div>
</div>

<div class="section" id="secAno">
  <h2>Signalements a revoir</h2>
  <div id="anomalies"></div>
</div>

<div class="section" id="secVid" style="display:none">
  <h2>Vidanges (config par engin)</h2>
  <div id="vidanges"></div>
</div>

<div class="section" id="secPan" style="display:none">
  <h2>Pannes frequentes</h2>
  <div id="pannes"></div>
</div>

<script>
var D = __DONNEES__;
var M = D.m, K = D.k;
var PAGE = 50;  // lignes visibles par page dans les longues listes
function tranche(arr, page) { return arr.slice(page.n * PAGE, (page.n + 1) * PAGE); }
function navHtml(nom, page, total) {
  var pages = Math.max(1, Math.ceil(total / PAGE));
  if (page.n >= pages) page.n = pages - 1;
  if (page.n < 0) page.n = 0;
  if (pages <= 1) return "";
  return "<div class='pager'><button onclick='" + nom + "(-1)'" + (page.n <= 0 ? " disabled" : "") + ">&larr; Precedent</button>" +
    "Page " + (page.n + 1) + " / " + pages + " (" + total + " lignes)" +
    "<button onclick='" + nom + "(1)'" + (page.n >= pages - 1 ? " disabled" : "") + ">Suivant &rarr;</button></div>";
}
var COUL = {"1":"#16a34a","2":"#0284c7","P":"#dc2626","E":"#eab308","SB":"#3DA5D9","F":"#94a3b8","A":"#8b5cf6","D":"#6d28d9","CP":"#111827"};

document.getElementById("periode").textContent =
  (M.chantier ? M.chantier + " - " : "") + (M.periode || "") +
  (M.source ? " (source : " + M.source + ")" : "");
if (M.demo) document.getElementById("demo").style.display = "";

var kpis = [
  [K.nb_engins, "engins suivis"],
  [K.heures_totales + " h", "heures valides du mois"],
  [K.nb_pannes_jours, "jours en panne (P)"],
  [K.nb_anomalies, "signalements a revoir"]
];
if (K.engins_unite_inconnue && K.engins_unite_inconnue.length)
  kpis.push([K.engins_unite_inconnue.length, "unite(s) a confirmer"]);
document.getElementById("kpis").innerHTML = kpis.map(function(k){
  return '<div class="carte"><div class="v">'+k[0]+'</div><div class="l">'+k[1]+'</div></div>';
}).join("");

// Filtres (visibles des que le parc depasse quelques engins)
var seuilFiltres = 10;
function enginsFiltres(){
  if (M.engins.length < seuilFiltres) return M.engins;
  var q = document.getElementById("fCode").value.trim().toLowerCase();
  var t = document.getElementById("fType").value;
  var c = document.getElementById("fChantier").value;
  var a = document.getElementById("fAlerte").value;
  return M.engins.filter(function(e){
    if (q && e.code.toLowerCase().indexOf(q) < 0) return false;
    if (t === "inc") { if (!e.uniteInconnue) return false; }
    else if (t && (e.uniteInconnue || e.type !== t)) return false;
    if (c && e.affectation !== c) return false;
    if (a === "sig" && !e.jours.some(function(j){ return j.st !== "OK"; })) return false;
    if (a === "saut" && !e.sauts.length) return false;
    if (a === "noprev" && e.prev && e.prev.estimation != null) return false;
    return true;
  });
}

// Grille
var maxJ = 0;
M.engins.forEach(function(e){ e.jours.forEach(function(j){ if (j.j > maxJ) maxJ = j.j; }); });
function dessinerGrille(liste){
var html = "<table><thead><tr><th class='codecol'>Engin</th>";
for (var d = 1; d <= maxJ; d++) html += "<th>" + d + "</th>";
html += "<th>Total</th></tr></thead><tbody>";
liste.forEach(function(e){
  var parJ = {}; e.jours.forEach(function(j){ parJ[j.j] = j; });
  html += "<tr><td class='codecol'>" + e.code + "</td>";
  for (var d = 1; d <= maxJ; d++) {
    var j = parJ[d];
    if (!j || !j.etat) { html += "<td></td>"; continue; }
    var cls = "cell e" + j.etat.replace(/[^A-Z0-9]/g,"");
    if (j.st === "A_VERIFIER") cls += " flague";
    if (j.st === "INVALIDE") cls += " invalide";
    var unite = e.type === "km" ? " km" : " h";
    var tip = e.code + " - " + (d<10?"0":"") + d + " | etat " + j.etat +
      (j.cpt != null ? " | compteur " + j.cpt : "") +
      (j.h != null ? " | " + j.h + unite : "") +
      (j.motif ? "\\n" + j.motif : "");
    html += "<td><span class='" + cls + "' title='" + tip.replace(/'/g,"&#39;") + "'>" + j.etat + "</span></td>";
  }
  html += "<td><b>" + (e.uniteInconnue ? "<span class='gA_VERIFIER'>a confirmer</span>" : (e.type === "km" ? e.totalKm + " km" : e.totalH)) + "</b></td></tr>";
});
html += "</tbody></table>";
return html;
}
var pageGrille = {n: 0};
var inconnus = M.engins.filter(function(e){ return e.uniteInconnue; }).map(function(e){ return e.code; });
function rendreGrille(){
  var liste = enginsFiltres();
  var html = dessinerGrille(tranche(liste, pageGrille)) + navHtml("navGrille", pageGrille, liste.length);
  if (inconnus.length)
    html += "<div class='note'>Unite du compteur a confirmer pour : " + inconnus.join(", ") +
      " - leurs releves depassent 24 h par jour, ce ne sont donc probablement pas des heures. " +
      "Ils sont EXCLUS des totaux d'heures (jamais devines). Si ce sont des compteurs " +
      "kilometriques, declarez-les dans votre config privee et ils compteront en km.</div>";
  document.getElementById("grille").innerHTML = html;
  return liste;
}
window.navGrille = function(d){ pageGrille.n += d; rendreGrille(); };
rendreGrille();

// Branchement des filtres : grille + repartition + liste du graphique
if (M.engins.length >= seuilFiltres) {
  document.getElementById("filtres").style.display = "";
  var chs = [];
  M.engins.forEach(function(e){ if (e.affectation && chs.indexOf(e.affectation) < 0) chs.push(e.affectation); });
  chs.sort().forEach(function(c){
    var o = document.createElement("option"); o.value = c; o.textContent = c;
    document.getElementById("fChantier").appendChild(o);
  });
  function appliquerFiltres(){
    pageGrille.n = 0; pageRep.n = 0;
    var liste = rendreGrille();
    dessinerRepartition(liste);
    remplirChoix(liste);
    document.getElementById("fCompte").textContent = liste.length + " / " + M.engins.length +
      " engins affiches (les indicateurs du haut restent le parc complet)";
  }
  ["fCode","fType","fChantier","fAlerte"].forEach(function(id){
    document.getElementById(id).addEventListener("input", appliquerFiltres);
    document.getElementById(id).addEventListener("change", appliquerFiltres);
  });
  document.getElementById("fCompte").textContent = M.engins.length +
    " engins affiches (les indicateurs du haut restent le parc complet)";
}

// Heures par jour
var choix = document.getElementById("choix");
function remplirChoix(liste){
  var courant = choix.value;
  choix.innerHTML = "";
  liste.filter(function(e){ return !e.uniteInconnue; }).forEach(function(e){
    var o = document.createElement("option");
    o.value = e.code; o.textContent = e.code + (e.type === "km" ? " (" + e.totalKm + " km)" : " (" + e.totalH + " h)");
    choix.appendChild(o);
  });
  if (courant && liste.some(function(e){ return e.code === courant; })) choix.value = courant;
  if (choix.options.length) { dessiner(choix.value); }
  else document.getElementById("totEngin").textContent = "Aucun engin avec des heures calculables dans cette selection.";
}
remplirChoix(M.engins);
function dessiner(code){
  var e = M.engins.filter(function(x){ return x.code === code; })[0];
  var unite = e.type === "km" ? " km" : " h";
  var vals = e.jours.filter(function(j){ return j.h != null; });
  var max = 0; vals.forEach(function(j){ if (j.h > max) max = j.h; });
  document.getElementById("bars").innerHTML = vals.map(function(j){
    var h = max ? Math.round(j.h / max * 138) : 0;
    return "<div class='bar' style='height:" + Math.max(h,2) + "px' onclick=" +
      "this.classList.toggle('actif')" +
      "><span class='val'>" + j.h + "</span>" +
      "<span class='tip'>jour " + j.j + " : " + j.h + unite + "</span></div>";
  }).join("");
  document.getElementById("axesx").innerHTML = vals.map(function(j){
    return "<span>" + j.j + "</span>";
  }).join("");
  document.getElementById("axey").innerHTML =
    "<span>" + max + unite + "</span><span>" + (Math.round(max/2*10)/10) + "</span><span>0</span>";
  document.getElementById("totEngin").textContent = e.type === "km"
    ? "Total valide : " + e.totalKm + " km sur le mois (compteur kilometrique). Les jours signales ne comptent pas. Toucher une barre pour le detail."
    : "Total valide : " + e.totalH + " h sur le mois. Les jours signales ne comptent pas. Toucher une barre pour le detail.";
}
choix.onchange = function(){ dessiner(choix.value); };

// Repartition
var ordre = ["1","2","P","E","SB","F","A","D","CP"];
var pageRep = {n: 0};
window.navRep = function(d){ pageRep.n += d; dessinerRepartition(enginsFiltres()); };
function dessinerRepartition(liste){
  document.getElementById("repartition").innerHTML = tranche(liste, pageRep).map(function(e){
    var tot = 0; ordre.forEach(function(k){ tot += e.etats[k] || 0; });
    if (!tot) return "";
    var seg = ordre.filter(function(k){ return e.etats[k]; }).map(function(k){
      var pct = (e.etats[k] / tot * 100);
      return "<div style='width:" + pct + "%;background:" + COUL[k] + "' title='" + k + " : " + e.etats[k] + " j (" + Math.round(pct) + "%)'></div>";
    }).join("");
    return "<div style='margin-bottom:8px'><span style='font-size:12px;font-weight:600'>" + e.code + "</span>" +
           "<div class='rep'>" + seg + "</div></div>";
  }).join("") + navHtml("navRep", pageRep, liste.length);
}
dessinerRepartition(M.engins);

// Anomalies
// Sauts de compteur + estimation de fin de mois
(function(){
  var lignesSauts = [], lignesPrev = [];
  M.engins.forEach(function(e){
    e.sauts.forEach(function(s){
      lignesSauts.push("<tr><td>" + e.code + "</td><td>" + s.jour + "</td><td>" +
        s.de + " &rarr; " + s.vers + "</td><td class='gINVALIDE'>+" + s.saut + "</td></tr>");
    });
    var u = e.type === "km" ? " km" : " h";
    if (e.prev && e.prev.estimation != null) {
      lignesPrev.push("<tr><td>" + e.code + "</td><td>" + e.prev.dernier_compteur + " (jour " + e.prev.dernier_jour + ")</td>" +
        "<td>~" + e.prev.estimation + u + "</td>" +
        "<td>rythme constate " + e.prev.rythme_jour + u + "/jour calendaire (" + e.prev.heures_base + u + " valides sur " + e.prev.jours_observe + " jours observes), " + e.prev.jours_restants + " jours restants</td></tr>");
    } else if (e.prev && e.prev.raison) {
      lignesPrev.push("<tr><td>" + e.code + "</td><td colspan='3'>" + e.prev.raison + "</td></tr>");
    }
  });
  if (lignesSauts.length || lignesPrev.length) {
    document.getElementById("secPrev").style.display = "";
    var pgSauts = {n: 0}, pgPrev = {n: 0};
    window.navSauts = function(d){ pgSauts.n += d; rendreSauts(); };
    window.navPrev = function(d){ pgPrev.n += d; rendrePrev(); };
    window.rendreSauts = function(){
      document.getElementById("sauts").innerHTML = lignesSauts.length
        ? "<h3 style='font-size:14px;margin:8px 0 4px'>Sauts detectes (exclus des totaux)</h3><table><thead><tr><th>Engin</th><th>Jour</th><th>Compteur</th><th>Saut</th></tr></thead><tbody>" + tranche(lignesSauts, pgSauts).join("") + "</tbody></table>" + navHtml("navSauts", pgSauts, lignesSauts.length)
        : "";
    };
    window.rendrePrev = function(){
      document.getElementById("previsions").innerHTML = lignesPrev.length
        ? "<h3 style='font-size:14px;margin:12px 0 4px'>Estimation du compteur en fin de mois</h3><table><thead><tr><th>Engin</th><th>Dernier compteur</th><th>Fin de mois estimee</th><th>Base de calcul</th></tr></thead><tbody>" + tranche(lignesPrev, pgPrev).join("") + "</tbody></table>" + navHtml("navPrev", pgPrev, lignesPrev.length)
        : "";
    };
    rendreSauts();
    rendrePrev();
  }
})();

var ano = document.getElementById("anomalies");
if (!M.anomalies.length) {
  ano.innerHTML = "<div class='note'>Aucun signalement : toutes les lignes sont coherentes.</div>";
} else {
  var lignesAno = M.anomalies.map(function(a){
    return "<tr class='ligne-anomalie'><td>" + a.engin + "</td><td>" + a.jour + "</td>" +
           "<td class='g" + a.gravite + "'>" + a.gravite + "</td><td>" + a.motif + "</td></tr>";
  });
  var pgAno = {n: 0};
  window.navAno = function(d){ pgAno.n += d; rendreAno(); };
  window.rendreAno = function(){
    ano.innerHTML = "<div class='note'>Ces lignes restent visibles dans la grille mais sont EXCLUES des totaux : les totaux sont donc provisoirement incomplets tant qu'elles ne sont pas revues par un humain. Les reglages par engin (compteur kilometrique, compteur fixe) se declarent dans la config, jamais devines.</div>" +
      "<table><thead><tr><th>Engin</th><th>Jour</th><th>Gravite</th><th>Motif</th></tr></thead><tbody>" +
      tranche(lignesAno, pgAno).join("") + "</tbody></table>" + navHtml("navAno", pgAno, lignesAno.length);
  };
  rendreAno();
}

// Sections optionnelles (mode CSV : vidanges + pannes)
if (M.vidanges && M.vidanges.length) {
  document.getElementById("secVid").style.display = "";
  var lignesVid = M.vidanges.map(function(v){
    var uv = v.unite || "h";
    return "<tr><td>" + v.code_engin + "</td><td>" + v.compteur_actuel + " " + uv + "</td><td>" + v.derniere_vidange +
      "</td><td>" + v.intervalle_h + " " + uv + "</td><td>" + v.heures_restantes + " " + uv + "</td><td>" + v.statut +
      (v.note ? " (" + v.note + ")" : "") + "</td></tr>";
  });
  var pgVid = {n: 0};
  window.navVid = function(d){ pgVid.n += d; rendreVid(); };
  window.rendreVid = function(){
    document.getElementById("vidanges").innerHTML =
      "<table><thead><tr><th>Engin</th><th>Compteur actuel</th><th>Derniere vidange</th><th>Intervalle</th><th>Reste</th><th>Statut</th></tr></thead><tbody>" +
      tranche(lignesVid, pgVid).join("") + "</tbody></table>" + navHtml("navVid", pgVid, lignesVid.length);
  };
  rendreVid();
}
if (M.pannes && M.pannes.length) {
  document.getElementById("secPan").style.display = "";
  var lignesPan = M.pannes.map(function(p){
    return "<tr><td>" + p.code_engin + "</td><td>" + p.type_panne + "</td><td>" + p.nb_fois + "</td><td>" + p.arret_total_h + "</td></tr>";
  });
  var pgPan = {n: 0};
  window.navPan = function(d){ pgPan.n += d; rendrePan(); };
  window.rendrePan = function(){
    document.getElementById("pannes").innerHTML =
      "<table><thead><tr><th>Engin</th><th>Type</th><th>Nb</th><th>Arret total h</th></tr></thead><tbody>" +
      tranche(lignesPan, pgPan).join("") + "</tbody></table>" + navHtml("navPan", pgPan, lignesPan.length);
  };
  rendrePan();
}
</script>
</body>
</html>
"""
