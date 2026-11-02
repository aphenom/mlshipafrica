# Intégration : zones 2 à 6, SMS HSMS, tenue à 1 000 colis par jour

Ce lot s'applique sur `main` (commit `1069b9a image page erreur`). Il contient 7 commits :

1. **Zones 2 à 6, grille ML COD, circuit des statuts, robustesse** (`core`, `management`)
2. **Module SMS HSMS** (nouvelle app `sms`, `settings.py`, `urls.py`)
3. **Ce guide** et `.env.example`
4. **Rôles, droits et journal d'audit** (voir section 9)
5. Mise à jour de ce guide
6. **Confirmation des commandes et acomptes** (voir section 10)
7. Mise à jour de ce guide

Aucune nouvelle dépendance Python : tout tourne avec le `requirements.txt` actuel.

---

## 1. Appliquer le patch

```bash
git checkout -b ml-cod-interieur/zones-sms-1000
git am ml-cod-interieur-*.patch        # ou : git pull du dépôt fourni
```

## 2. Tester d'abord en recette (base copiée de la production)

```bash
cd mlshipafrica
python manage.py migrate                               # core 0007-0009, management 0022-0025, sms 0001-0002
python manage.py test management sms                   # 51 tests, tous doivent passer
python manage.py appliquer_grille_ml_cod --dry-run     # LIRE le rapport : rien n'est écrit
```

Dans le rapport du `--dry-run`, vérifier :

- **Localités changées de zone** : par exemple Bouaké passe de l'ancienne « Zone 2 » à la nouvelle « Zone 3 ». C'est normal : la numérotation est maintenant celle du réseau, de 2 à 6.
- **Localités retirées** : villes de l'ancienne base absentes de la liste officielle des 275. Elles ne sont plus proposées aux vendeurs, mais rien n'est supprimé. Si une ville manque à tort, ajoutez-la dans `management/grille_ml_cod.py` (ou une orthographe dans `ALIAS`) et relancez.
- **Tarifs propres à un vendeur, à revoir** : ils ne sont jamais modifiés automatiquement. Ils visaient les anciennes zones, donc ils ne s'appliquent plus tant qu'ils ne sont pas recréés sur les nouvelles zones.

Puis appliquer :

```bash
python manage.py appliquer_grille_ml_cod --couts /chemin/hors-depot/couts_partenaire.json
```

> **Coûts partenaire.** Ils ne sont jamais dans le code : le dépôt GitHub est public. Le fichier JSON est remis à part par la direction et doit rester hors du dépôt. Sans `--couts`, la commande ne touche pas aux coûts déjà saisis, et la direction peut les saisir dans Paramètres › Tarifications.

La commande est rejouable : la relancer ne crée pas de doublon.

## 3. Variables d'environnement (`.env`)

Voir `.env.example`. Nouvelles variables :

| Variable | Rôle |
|---|---|
| `HSMS_EMAIL`, `HSMS_PASSWORD` | Compte HSMS (connexion pour obtenir le jeton) |
| `HSMS_CLIENT_ID`, `HSMS_CLIENT_SECRET` | Application HSMS (envoi) |
| `HSMS_WEBHOOK_SECRET` | Secret long et aléatoire, placé dans l'URL du webhook des accusés |
| `ADMIN_URL` | Adresse de l'administration Django (par défaut `direction-mlcod/`) |
| `DB_CONN_MAX_AGE` | Durée de vie des connexions MySQL, en secondes (par défaut 60) |

## 4. Tâches planifiées

```bash
python manage.py crontab add      # installe les 3 tâches ci-dessous
python manage.py crontab show
```

| Quand | Commande | Rôle |
|---|---|---|
| chaque minute | `sms_envoyer` | Envoie les SMS en file |
| toutes les 10 min | `sms_accuses` | Statuts de livraison (secours du webhook) et solde |
| 19 h | `sms_resume_soir` | Résumé aux vendeurs. Ne fait rien tant qu'il est désactivé |

Les tâches ne se chevauchent pas (`CRONTAB_LOCK_JOBS`). Leurs journaux vont dans `logs/cron_sms.log`.

## 5. Mise en service des SMS

1. Créer ou désigner un compte super-utilisateur pour la direction : `python manage.py createsuperuser`, ou cocher `is_superuser` sur le compte du CEO.
2. Tester HSMS sans rien activer : `python manage.py sms_test 07XXXXXXXX`. La commande affiche la réponse brute de HSMS. **Vérifier que le ticket est bien lu**, car la documentation HSMS ne montre pas la réponse de l'envoi. S'il manque, ajuster `extraire_tickets` dans `sms/hsms.py`.
3. Chez HSMS, déclarer l'URL de webhook (mode DLR Push) : `https://app.mlcodinterieur.com/sms/hsms/accuses/<HSMS_WEBHOOK_SECRET>/`
4. Dans `/<ADMIN_URL>` › Paramètres SMS : vérifier le numéro service client, puis cocher **Envoi des SMS activé**. Avant cela, les SMS sont préparés dans la file mais ne partent pas.
5. Dans `/<ADMIN_URL>` › Modèles de SMS, les textes sont modifiables. Le coût estimé (nombre de SMS) s'affiche.

**SMS envoyés (plan validé le 29/10/2026)**

| Évènement | Client | Vendeur |
|---|---|---|
| Ramassé ou Déposé (reçu chez nous) | Oui : montant, ville, date prévue | Non |
| Arrivé à destination | Oui | Non |
| Échec de livraison | Oui, la 1re fois seulement | Non |
| Annulé avant expédition | Oui | Oui |
| En transit, en livraison, livré, retour | Non | Non |
| Résumé du jour, 19 h | Non | Oui, si activé |

Les SMS partent entre 7 h et 21 h (heure d'Abidjan). Un SMS créé la nuit part à 7 h.

## 6. Ce qui change pour les utilisateurs

- **Vendeurs** : chaque localité est affichée avec sa zone et son délai (« Bouaké · Zone 3 · J+3 à J+4 »). Le format Grand n'est plus proposé tant qu'il n'a pas de tarif. Une destination sans tarif affiche un message clair au lieu d'une page d'erreur.
- **Équipe** :
  - nouveaux statuts « Échec de livraison » et « Annulé avant expédition » ;
  - relance possible après une annulation ;
  - filtres de liste `?type_colis=echec_livraison` et `?type_colis=annule` (liens à ajouter au menu) ;
  - l'historique des livrés affiche les 60 derniers jours (`?jours=180` pour élargir).
- **Direction** : coût partenaire par tarif, visible uniquement par le super administrateur et la comptable.

## 7. Tenue à 1 000 colis par jour : ce qui est fait, ce qui reste

**Fait dans ce lot**

- Listes des colis : le nombre de requêtes SQL ne dépend plus du nombre de colis (27 requêtes pour 500 colis, contre 1 007 avant). Ce point est vérifié par un test automatique.
- Index sur les colonnes filtrées (statut, vendeur, date) et sur l'historique.
- Les SMS ne sont jamais envoyés pendant la requête web : une panne de HSMS ne ralentit pas l'équipe.
- Connexions MySQL réutilisées (`CONN_MAX_AGE`).
- Suppression des `dd()` qui affichaient des données à l'écran en cas d'erreur, et bloquaient l'import des vendeurs.

**À traiter ensuite (non bloquant pour démarrer)**

1. **Pagination côté serveur** des listes. Aujourd'hui toute la liste est envoyée au navigateur. C'est tenable pour les colis « en cours », mais pas sur plusieurs mois.
2. **Dépôt public.** Le code est visible de tous sur GitHub. Le passer en privé (Settings › Danger Zone › Change visibility).
3. **Encodage `utf8` (3 octets) de MySQL.** Un emoji dans un nom de boutique ou une adresse fait échouer l'enregistrement. Il faut passer en `utf8mb4` : conversion de la base, à planifier hors des heures de travail.
4. **Sauvegarde quotidienne de la base**, avec un test de restauration mensuel.
5. **Codes uniques** (`CodeGenerator`) : en cas de collision simultanée, l'enregistrement échoue au lieu de retenter. C'est très rare au volume visé, mais à couvrir par une nouvelle tentative sur `IntegrityError`.

## 8. Retour arrière

- Couper les SMS : décocher « Envoi des SMS activé », ou `python manage.py crontab remove`.
- Code : `git revert` des commits. Les migrations ne font qu'ajouter des colonnes, des tables et des index (aucune suppression). `appliquer_grille_ml_cod` ne supprime rien : les anciennes zones et les anciens tarifs sont seulement désactivés, et peuvent être réactivés dans Paramètres.

## 9. Rôles, droits et journal d'audit (commit 4)

**Les 6 rôles de l'équipe** (le 7e est le vendeur) :

| Rôle (valeur en base) | Voit l'argent de la société | Peut faire |
|---|---|---|
| CEO (`super`) | Oui | Tout, y compris tarifs, coût partenaire, nom du prestataire, configuration, journal d'audit |
| Comptable (`comptable`) | Oui | Paiements des frais, reversements, journaux d'argent, liste des colis et des vendeurs |
| Manager (`manager`) | Non | Colis : voir, faire avancer, annuler le dernier mouvement ; journal des mouvements ; vendeurs (lecture) |
| Agent COD (`agent`) | Non | Colis : voir et faire avancer |
| Commercial (`commercial`) | Non | Ses vendeurs : approuver, activer, désactiver, affecter un agent COD |
| Administrateur technique (`administrateur`) | Non | Zones, localités, formats, comptes de l'équipe, import des vendeurs |

- **Une seule table de droits** : `mlshipafrica/droits.py`. Chaque vue est protégée par `@droit_requis(...)` côté serveur. Une URL d'un autre rôle renvoie 403, et chaque action POST (mouvement, annulation, paiement, reversement, suppression de vendeur) est revérifiée.
- **Montants masqués** : les gabarits affichent les montants seulement avec `{% if 'argent' in droits %}`. C'est le cas du tableau de bord, de la liste des colis, du détail colis (y compris le JavaScript du paiement) et du classement des vendeurs. Le menu suit les mêmes droits.
- **Détail colis limité à la licence** de l'utilisateur.
- **Commercial** : il ne voit que ses vendeurs et ceux qui attendent une approbation. Celui qui approuve un vendeur en devient le commercial.
- **Vendeur** : nouveaux champs `commercial` et `agent_cod`, avec un bloc d'affectation sur la fiche vendeur.
- **Rôles réservés** : seul le CEO peut attribuer les rôles CEO ou comptable.
- **Journal d'audit** (`core/audit.py`, modèle `JournalAudit`) : création et modification des tarifs, zones, localités, vendeurs, comptes, colis, mouvements, paiements, reversements et paramètres SMS, avec l'auteur, son rôle, l'avant et l'après. Il se consulte en lecture seule dans `/<ADMIN_URL>`.

**Avant la mise en ligne, obligatoire** : avant ce lot, « administrateur » faisait presque tout. Après le déploiement, un administrateur ne voit plus ni les colis ni l'argent. Il faut donc attribuer à chaque compte son vrai rôle :

```bash
python manage.py roles_equipe                                   # liste les comptes, leur rôle et leurs droits
python manage.py roles_equipe --attribuer agent1@exemple.ci agent
```

Le compte du CEO doit être en `super`, et `is_superuser` pour l'administration Django.

Correction au passage : le détail d'un colis plantait (erreur 500) quand un mouvement avait été créé sans utilisateur (tâche, import).

## 10. Confirmation des commandes et acomptes (commit 6)

**Parcours**

1. Quand le vendeur valide sa commande, elle entre dans la **file de confirmation** (menu « Confirmations »), affectée à l'agent COD du vendeur.
2. L'agent appelle le client et enregistre le résultat. Chaque appel est gardé dans l'historique du colis.
   - **Confirmé** : avec acompte (réseau Orange, MTN, Moov ou Wave, référence et numéro du dépôt) ou sans.
   - **Injoignable** : le colis reste dans la file, dans « À rappeler ».
   - **Annulé** : le motif est obligatoire. Le colis passe « Annulé avant expédition » et le vendeur reçoit le SMS.
3. **Annulation avant le départ** (par la file ou par le détail du colis) : l'acompte reçu passe « à rembourser ».
4. **Annulation après le départ** (en transit ou plus loin) : aucun remboursement. Le circuit des statuts l'interdit de toute façon.
5. **Relance** : le colis revient à son statut d'avant l'annulation et doit être reconfirmé. L'acompte reste à rembourser, la comptable décide.
6. La comptable voit les acomptes dans le menu « Acomptes clients » (à rembourser, reçus, remboursés). Elle marque un remboursement avec sa référence.

**Règles côté serveur**

- Un colis non confirmé ne passe en transit qu'avec un motif écrit dans le commentaire.
- Une annulation demande toujours un motif.
- Une même référence de dépôt ne peut pas servir à deux commandes (contrainte en base).

**Qui voit quoi**

- La file de confirmation est ouverte au CEO, au manager et aux agents. Un agent voit ses colis et ceux sans agent. Le manager filtre par agent.
- La page des acomptes est réservée au CEO et à la comptable.
- Sur la page d'un colis, le manager voit l'état de l'acompte mais ni la référence ni le montant.
- **Le vendeur ne voit jamais l'acompte.** Un test vérifie que le mot n'apparaît sur aucune de ses pages.
- Le montant de l'acompte se règle dans la configuration (`montant_acompte`, 2 000 F par défaut).

**Reprise de l'existant**

- La migration 0025 marque « confirmés » les colis déjà partis, pour qu'ils n'encombrent pas la file des agents.
- Les colis encore chez le vendeur ou au hub entrent dans la file.
- L'agent COD affecté au vendeur est reporté sur ses colis.
