"""
Messages automatiques réglés par le CEO : un modèle par évènement, SMS et/ou e-mail (e-mail : vendeur seulement).

Par défaut, seuls les SMS du plan validé le 29/10/2026 restent actifs côté client (reçu, arrivé, 1er échec, annulé) ;
les nouveaux SMS de statut sont créés désactivés : le CEO les active s'il le veut (coût par SMS).
"""
from django.db import migrations

# cle, libellé, destinataire, rubrique, ordre, SMS actif, texte SMS, e-mail actif, objet, texte e-mail
NOUVEAUX = [
    ('v_bienvenue', "Vendeur : inscription reçue, compte en cours d'approbation", 'vendeur', 'compte', 1, True,
     "Bienvenue chez ML COD Interieur, {vendeur} ! Votre compte est en cours d'approbation. Nous vous appelons tres vite. Info : {tel}",
     True, "Bienvenue chez ML COD Intérieur",
     "Bonjour {contact},\n\nMerci pour votre inscription, {vendeur} ! Votre compte est en cours d'approbation : notre équipe vous appelle très vite pour finaliser.\n\nPour toute question : {tel}.\n\nL'équipe ML COD Intérieur"),
    ('v_approuve', "Vendeur : compte approuvé", 'vendeur', 'compte', 2, True,
     "ML COD Interieur : bonne nouvelle {vendeur}, votre compte est approuve ! Connectez-vous et creez votre premiere commande. Info : {tel}",
     True, "Votre compte ML COD Intérieur est approuvé",
     "Bonjour {contact},\n\nBonne nouvelle : le compte {vendeur} est approuvé. Vous pouvez dès maintenant vous connecter et créer votre première commande.\n\nPour toute question : {tel}.\n\nL'équipe ML COD Intérieur"),
    ('cl_transit', "Client : colis en route vers sa ville", 'client', 'livraison', 12, False,
     "{vendeur} : votre colis {ref} est en route vers {ville}. Preparez {montant} pour la livraison. Info : {tel}", False, '', ''),
    ('cl_en_livraison', "Client : colis en cours de livraison", 'client', 'livraison', 14, False,
     "{vendeur} : votre colis arrive aujourd'hui a {ville}. Preparez {montant}, le livreur vous appelle. Info : {tel}", False, '', ''),
    ('cl_livre', "Client : colis livré", 'client', 'livraison', 15, False,
     "{vendeur} : votre colis {ref} est livre. Merci pour votre confiance !", False, '', ''),
    ('v_recu', "Vendeur : colis reçu chez nous", 'vendeur', 'livraison', 31, False,
     "MLCOD : colis {ref} recu ({client}, {ville}).", False, "Colis {ref} reçu",
     "Bonjour {vendeur},\n\nLe colis {ref} pour {client} ({ville}) est bien reçu chez ML COD Intérieur.\nProduit : {produit} x{quantite} · à encaisser : {montant}.\n\nL'équipe ML COD Intérieur"),
    ('v_transit', "Vendeur : colis en transit", 'vendeur', 'livraison', 32, False,
     "MLCOD : colis {ref} en route vers {ville}.", False, "Colis {ref} en route vers {ville}",
     "Bonjour {vendeur},\n\nLe colis {ref} pour {client} est en route vers {ville}.\n\nL'équipe ML COD Intérieur"),
    ('v_arrive', "Vendeur : colis arrivé dans la ville du client", 'vendeur', 'livraison', 33, False,
     "MLCOD : colis {ref} arrive a {ville}.", False, "Colis {ref} arrivé à {ville}",
     "Bonjour {vendeur},\n\nLe colis {ref} pour {client} est arrivé à {ville}.\n\nL'équipe ML COD Intérieur"),
    ('v_en_livraison', "Vendeur : colis en cours de livraison", 'vendeur', 'livraison', 34, False,
     "MLCOD : colis {ref} en cours de livraison a {ville}.", False, "Colis {ref} en cours de livraison",
     "Bonjour {vendeur},\n\nLe colis {ref} pour {client} est en cours de livraison à {ville}.\n\nL'équipe ML COD Intérieur"),
    ('v_livre', "Vendeur : colis livré", 'vendeur', 'livraison', 35, False,
     "MLCOD : colis {ref} livre a {client} ({montant}).", False, "Colis {ref} livré",
     "Bonjour {vendeur},\n\nLe colis {ref} est livré à {client} ({ville}). Montant encaissé : {montant}.\nIl entrera dans votre prochain paiement.\n\nL'équipe ML COD Intérieur"),
    ('v_echec', "Vendeur : échec de livraison", 'vendeur', 'livraison', 36, False,
     "MLCOD : echec de livraison pour {ref} ({client}, {ville}). Detail dans votre espace.", False, "Échec de livraison : colis {ref}",
     "Bonjour {vendeur},\n\nLa livraison du colis {ref} à {client} ({ville}) n'a pas pu se faire. Nous vous tenons informé dans votre espace.\n\nL'équipe ML COD Intérieur"),
    ('v_retourne', "Vendeur : colis retourné au vendeur", 'vendeur', 'retours', 60, False,
     "MLCOD : colis {ref} vous a ete retourne.", False, "Colis {ref} retourné",
     "Bonjour {vendeur},\n\nLe colis {ref} vous a été retourné.\n\nL'équipe ML COD Intérieur"),
    ('v_facture', "Vendeur : facture de paiement émise", 'vendeur', 'paiement', 80, False,
     "MLCOD : facture de paiement {facture} emise, net {montant}. Detail dans votre espace.", True,
     "Facture de paiement {facture}",
     "Bonjour {vendeur},\n\nVotre facture de paiement {facture} est émise. Net à recevoir : {montant}.\nLe détail colis par colis est dans « Mon argent ».\n\nL'équipe ML COD Intérieur"),
    ('v_verse', "Vendeur : paiement envoyé", 'vendeur', 'paiement', 81, True,
     "MLCOD : paiement envoye, {montant_envoye} par {moyen} (facture {facture}). Merci !", True,
     "Paiement envoyé : {montant_envoye}",
     "Bonjour {vendeur},\n\nNous venons de vous envoyer {montant_envoye} par {moyen} (facture {facture}, référence {reference}).\n\nL'équipe ML COD Intérieur"),
    ('v_stockage', "Vendeur : stockage du mois chargé", 'vendeur', 'paiement', 83, False,
     "MLCOD : stockage de {mois} : {pieces} pieces, {montant}. Deduit de votre prochain paiement.", True,
     "Stockage de {mois}",
     "Bonjour {vendeur},\n\nLe stockage de {mois} est chargé : {pieces} pièces chez nous, soit {montant}. Il sera déduit de votre prochain paiement.\n\nL'équipe ML COD Intérieur"),
]

EXISTANTS = {  # rubrique et ordre des modèles déjà en place
    'cl_recu': ('livraison', 11), 'cl_arrive': ('livraison', 13), 'cl_echec': ('livraison', 16), 'cl_annule': ('livraison', 17),
    'v_annule_av': ('livraison', 37), 'retour': ('retours', 61), 'rappel_subst': ('retours', 62), 'ret_alerte': ('retours', 63),
    'ret_abandon': ('retours', 64), 'ret_abandon_def': ('retours', 65), 'v_stock': ('paiement', 84), 'moyen': ('paiement', 85),
    'recap': ('livraison', 40),
}


def creer(apps, schema_editor):
    SmsModele = apps.get_model('sms', 'SmsModele')
    for cle, (cat, ordre) in EXISTANTS.items():
        SmsModele.objects.filter(cle=cle).update(categorie=cat, ordre=ordre)
    for cle, lib, dest, cat, ordre, sms, texte, mail, objet, corps in NOUVEAUX:
        SmsModele.objects.get_or_create(cle=cle, defaults={
            'libelle': lib, 'destinataire': dest, 'categorie': cat, 'ordre': ordre, 'actif': sms, 'texte': texte,
            'email_actif': mail, 'email_objet': objet, 'email_texte': corps, 'priorite': 5})


class Migration(migrations.Migration):
    dependencies = [('sms', '0005_messages_auto')]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
