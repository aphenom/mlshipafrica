# Version de test (recette) de ML COD Intérieur

But : tester la nouvelle version **avec les vraies données d'aujourd'hui**, sans jamais toucher la plateforme en ligne.
La recette est une **copie** : sa propre base, ses propres fichiers, son propre sous-domaine. Rien n'en sort.

## Ce que garantit le mode RECETTE (`RECETTE=True` dans le `.env` de la recette)

- Bandeau orange « VERSION DE TEST » sur toutes les pages.
- **Aucun SMS** ne part (la file reste en base), **aucun envoi à Woura ni aux webhooks des vendeurs**, e-mails écrits dans le journal au lieu d'être envoyés.
- Garde-fou : l'application refuse de démarrer si `RECETTE=True` et que le nom de la base ne contient pas « recette ».
- La commande `recette_preparer` refuse de tourner hors recette.
- **Ne pas** lancer `python manage.py crontab add` dans la recette.

## Mise en place (développeur, sur le serveur, ~10 minutes)

```bash
PROD_DIR=/chemin/du/code/en/ligne/mlshipafrica \
RECETTE_DIR=/var/www/mlcod-recette \
BRANCHE=ml-cod-interieur/recette-18-11 \
RECETTE_DOMAINE=recette.mlcodinterieur.com \
MOT_DE_PASSE='un-mot-de-passe-de-test' \
bash recette/creer_recette.sh
```

Le script :
1. copie la base de production vers `<base>_recette` (`mysqldump --single-transaction` : lecture seule, sans bloquer la production) ;
2. récupère le code de la branche dans un dossier séparé ;
3. écrit le `.env` de la recette (base `_recette`, médias et statiques séparés, `RECETTE=True`) ;
4. migre la copie et collecte les fichiers statiques ;
5. donne le même mot de passe à tous les comptes (pour tester chaque rôle), coupe les envois et liste un compte par rôle ;
6. affiche, en simulation, l'effet du taux de collecte de 5 % sur les colis existants.

Puis servir la recette sur un sous-domaine (exemple Nginx + Gunicorn) :

```bash
cd /var/www/mlcod-recette/mlshipafrica && gunicorn mlshipafrica.wsgi -b 127.0.0.1:8010 --workers 2
```

```nginx
server {
    server_name recette.mlcodinterieur.com;
    auth_basic "Recette ML COD"; auth_basic_user_file /etc/nginx/recette.htpasswd;   # accès réservé
    location /static/ { alias /var/www/mlcod-recette/static_recette/; }
    location /media/  { alias /var/www/mlcod-recette/media_recette/; }
    location / { proxy_pass http://127.0.0.1:8010; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
}
```

Rafraîchir les données : relancer le script (la copie est refaite à neuf). Tout ce qui a été testé dans la recette est effacé.

## Parcours de test conseillé (une personne par rôle)

1. **Agent COD** : Shipping → filtrer par statut « En transit » → cocher → « Passer au statut » Arrivé ; ouvrir un colis → écrire un message.
2. **Manager** : cocher des colis → Feuille de route, Étiquettes, Fiche de préparation ; corriger un statut avec une raison ; valider un envoi de stock (photos).
3. **Comptable** : Paiements vendeurs → 1 · Livrés à valider (filtrer la période) → Passer en Unpaid → 2 · À payer → Générer → 3 · Verser.
4. **Vendeur** : Mon argent (factures ligne par ligne, contester) ; Nouvelle commande → « Valider et créer une autre » ; Importer un fichier ; Paramètres › Numéro de paiement.
5. **CEO** : Paramètres › Frais et réglages (taux 5 %, simulation) ; cloche ; modifier une commande.

## Mise en ligne après validation

1. Sauvegarde de la base de production.
2. Déployer la branche, `python manage.py migrate`, `collectstatic`.
3. `python manage.py crontab remove && python manage.py crontab add` (la tâche des relevés automatiques est retirée).
4. Le CEO applique le taux de collecte aux colis existants depuis **Paramètres › Frais et réglages** (ou `python manage.py appliquer_taux_collecte --appliquer`).
