# Suivi de parc engins : pointage, pannes, vidanges et tableau de bord

Projet Python personnel de **suivi d'un parc d'engins de chantier** :
contrôle des pointages journaliers (état + compteur), heures de
fonctionnement, pannes récurrentes, vidanges, et un **tableau de bord
HTML autonome** généré à partir des données.

Projet personnel, utilisable sans aucune configuration.
Aucune donnée d'entreprise, aucune URL, aucun identifiant dans ce dépôt.
Le script **signale** les anomalies ; il ne corrige jamais les données
d'origine et la décision finale reste à l'humain.

Python 3 standard, **aucune bibliothèque à installer**, aucun service
externe obligatoire. Le tableau de bord est une page HTML autonome (sans
CDN) qui s'ouvre dans n'importe quel navigateur.

## Ce qu'il fait

1. **Import des pointages réels** (deux sources possibles, même donnée :
   état + compteur par engin et par jour) :
   - la grille **Consulter** de l'application de pointage de
     l'entreprise, récupérée automatiquement en **lecture seule**
     (`--fetch`) ou sauvegardée en HTML (`--consulter`) ;
   - l'état Excel **Fiche de pointage** téléchargé à la main (`--excel`).
2. **Contrôle et calculs** : heures du jour = compteur du jour −
   compteur du jour précédent. Le script signale :
   - compteur en baisse → **invalide** (exclu des totaux) ;
   - saut > 24 h sur un compteur horaire → **invalide** ;
   - état travail (1/2) sans hausse du compteur → **à vérifier** ;
   - hausse du compteur avec état P/E/SB/F → **à vérifier** ;
   - premier jour du mois sans compteur de fin du mois précédent →
     heures non calculables (signalé, jamais inventé).
   Les lignes signalées restent **visibles mais exclues des totaux**.
   Un engin à compteur kilométrique se déclare en config
   (`"type_compteur": "km"`) : ses kilomètres sont suivis à part, sans
   la règle des 24 h. Un engin à compteur bloqué à zéro se déclare avec
   `"compteur_fixe": true`.
3. **Tableau de bord** (`rapports/dashboard.html`) : indicateurs du
   mois, grille des états journaliers colorée avec survol (compteur,
   heures, motif), **recherche et filtres** (code, type de compteur,
   chantier, signalements/sauts), heures par jour par engin,
   répartition des états, **sauts de compteur** détectés et
   **estimation du compteur en fin de mois** (projection clairement
   étiquetée, au rythme constaté en unités/jour calendaire, ancrée sur
   la dernière lecture valide ; aucune estimation si l'unité est à
   confirmer ou si les données ne suffisent pas), liste des signalements,
   et, avec le jeu de données fourni, le suivi des **vidanges** (intervalle
   réglable par engin, en heures ou en km) et des **pannes
   fréquentes**.

## Utilisation

Essai rapide (aucune configuration requise) :

```bash
python3 main.py                              # contrôle CSV + rapports + dashboard.html
python3 -m unittest discover -s tests -v     # tests
python3 generer_parc.py                 # régénère le jeu de données de data/
```

Le dossier `data/` contient un **jeu de données de 400 engins** généré par
`generer_parc.py` (graine fixe, reproductible) : 300 camions à
compteur kilométrique et 100 engins de chantier à compteur horaire,
avec les défauts réalistes d'une saisie manuelle (lectures manquantes,
doublons, compteurs qui reculent, journées invraisemblables, 4 engins
dont l'unité est à confirmer, machines arrivées en cours de mois). Il
sert à voir l'outil à l'échelle d'un vrai parc.

Avec les données réelles (fichiers privés, **hors dépôt**) :

```bash
# A. récupération automatique de la grille Consulter (lecture seule)
python3 main.py --fetch --chantier-id 1234 --annee 2026 --mois 11

# B. ou à partir d'un fichier déjà téléchargé
python3 main.py --consulter grille.html --annee 2026 --mois 11
python3 main.py --excel FichePointage.xlsx --annee 2026 --mois 11
```

### Connexion automatique (--fetch)

`--fetch` lit l'adresse du site et les identifiants dans
**`config.local.json`**, un fichier privé à la racine du projet,
**ignoré par git** (voir `.gitignore`) et jamais commit :

```json
{
  "url_base": "https://.../Pointages",
  "utilisateur": "...",
  "mot_de_passe": "..."
}
```

Le script se contente de lire : il n'écrit, ne modifie ni ne supprime
jamais rien sur le site. Les fichiers téléchargés et les rapports
générés (`rapports/`, `*.xlsx`, `data_prive/`) sont également ignorés
par git : **aucune donnée de l'entreprise ne peut finir dans le dépôt
ou sur GitHub**.

## Fichiers

```
main.py               point d'entrée (démo CSV + imports réels + tableau de bord)
pointage_import.py     parseurs (grille Consulter HTML, état Excel) et règles de contrôle
fetch_pointage.py     connexion lecture seule à la grille Consulter (config privée)
dashboard.py          génération du tableau de bord HTML autonome
generer_parc.py       générateur du jeu de données (400 engins)
data/*.csv, config    données générées (régénérables)
tests/                tests automatiques (logique + parseurs sur fixtures fabriquées)
rapports/             sorties (ignoré par git)
```

## Limites assumées

- La récupération automatique (`--fetch`) suit la structure réelle du
  site (formulaire de connexion, grille Consulter) vérifiée pendant le
  développement, mais son exécution complète de bout en bout reste à
  valider sur un poste ayant accès au site ; en attendant,
  `--consulter` et `--excel` donnent exactement le même résultat.
- Le 1er du mois ne peut pas être calculé sans le compteur de fin du
  mois précédent (importer deux mois ou saisir la référence).
- Les règles de seuil (24 h/jour) valent pour des compteurs horaires ;
  déclarer les compteurs kilométriques en config.
- Le suivi des vidanges et des pannes avec vos propres données nécessite leurs
  données (CSV privés) : seul le pointage est importé automatiquement.

## Auteur

Projet personnel de **Rachid Fadili**, conçu à partir de son
expérience terrain dans le suivi d'engins de chantier.
Contact : rachidfadili2002@outlook.com
GitHub : https://github.com/rachidfadili-ai
