#!/usr/bin/env bash
# Crée (ou rafraîchit) la version de test de ML COD Intérieur à côté de la production, sans jamais la modifier.
# À lancer sur le serveur, par le développeur. Voir RECETTE.md pour le détail.
#
#   PROD_DIR=/chemin/du/code/en/ligne  RECETTE_DIR=/var/www/mlcod-recette  BRANCHE=ml-cod-interieur/recette-18-11 \
#   MOT_DE_PASSE='Test2026!'  bash recette/creer_recette.sh
set -euo pipefail

: "${PROD_DIR:?PROD_DIR = dossier du code en production (celui qui contient manage.py)}"
: "${RECETTE_DIR:?RECETTE_DIR = dossier de la recette, différent de PROD_DIR}"
: "${BRANCHE:?BRANCHE = branche à tester}"
: "${MOT_DE_PASSE:?MOT_DE_PASSE = mot de passe commun des comptes de test}"
[ "$(realpath "$PROD_DIR")" != "$(realpath -m "$RECETTE_DIR")" ] || { echo "RECETTE_DIR doit être différent de PROD_DIR"; exit 1; }

ENV_PROD="$PROD_DIR/.env"; [ -f "$ENV_PROD" ] || ENV_PROD="$PROD_DIR/../.env"
[ -f "$ENV_PROD" ] || { echo ".env de production introuvable (ni $PROD_DIR/.env ni ../.env)"; exit 1; }
lire() { grep -E "^$1=" "$ENV_PROD" | head -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'; }
DB_PROD=$(lire DB_NAME); DB_USER=$(lire DB_USER); DB_PASS=$(lire DB_PASSWORD); DB_HOST=$(lire DB_HOST)
DB_RECETTE="${DB_PROD}_recette"
export MYSQL_PWD="$DB_PASS"

echo "1/6 Copie de la base $DB_PROD → $DB_RECETTE (lecture seule sur la production)"
mysqldump --single-transaction --quick --routines -h "$DB_HOST" -u "$DB_USER" "$DB_PROD" > /tmp/mlcod_prod.sql
mysql -h "$DB_HOST" -u "$DB_USER" -e "DROP DATABASE IF EXISTS \`$DB_RECETTE\`; CREATE DATABASE \`$DB_RECETTE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -h "$DB_HOST" -u "$DB_USER" "$DB_RECETTE" < /tmp/mlcod_prod.sql
rm -f /tmp/mlcod_prod.sql

echo "2/6 Code de la branche $BRANCHE dans $RECETTE_DIR"
if [ -d "$RECETTE_DIR/.git" ]; then git -C "$RECETTE_DIR" fetch origin && git -C "$RECETTE_DIR" checkout -B "$BRANCHE" "origin/$BRANCHE"
else git clone --branch "$BRANCHE" "$(git -C "$PROD_DIR" remote get-url origin)" "$RECETTE_DIR"; fi

APP="$RECETTE_DIR/mlshipafrica"; [ -f "$APP/manage.py" ] || APP="$RECETTE_DIR"
echo "3/6 .env de la recette (base, médias et fichiers statiques séparés, RECETTE=True)"
mkdir -p "$RECETTE_DIR/media_recette" "$RECETTE_DIR/static_recette"
MEDIA_PROD=$(lire MEDIA_ROOT); [ -n "$MEDIA_PROD" ] && [ -d "$MEDIA_PROD" ] && rsync -a "$MEDIA_PROD"/ "$RECETTE_DIR/media_recette"/ || true
grep -vE '^(DB_NAME|RECETTE|DEBUG|MEDIA_ROOT|STATIC_ROOT|ALLOWED_HOSTS_EN_PLUS)=' "$ENV_PROD" > "$APP/.env"
cat >> "$APP/.env" <<FIN
DB_NAME=$DB_RECETTE
RECETTE=True
DEBUG=False
MEDIA_ROOT=$RECETTE_DIR/media_recette/
STATIC_ROOT=$RECETTE_DIR/static_recette/
ALLOWED_HOSTS_EN_PLUS=${RECETTE_DOMAINE:-recette.mlcodinterieur.com}
FIN
[ -f "$PROD_DIR/couts_partenaire.json" ] && cp "$PROD_DIR/couts_partenaire.json" "$APP/" || true

echo "4/6 Dépendances, migrations, fichiers statiques"
cd "$APP"
python -m pip install -q -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput -v 0

echo "5/6 Comptes de test et envois coupés"
python manage.py recette_preparer --mot-de-passe "$MOT_DE_PASSE"

echo "6/6 Taux de collecte (simulation, rien n'est appliqué) :"
python manage.py appliquer_taux_collecte

echo
echo "Recette prête. Démarrer : gunicorn mlshipafrica.wsgi -b 127.0.0.1:8010 (voir RECETTE.md pour le sous-domaine)."
echo "NE PAS lancer « crontab add » dans la recette."
