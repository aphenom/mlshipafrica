from django_dump_die.middleware import dd

from management.models import Article, Vendeur

from mlshipafrica.enums import StatutTraitement, StatutVendeur, TypeProfilStaffChoice, TypeVendeurChoice, array_statut_traitement_retour, array_statut_traitement_en_cours, array_statut_traitement_livre

from management.resources import VendeurResource

from django.utils import timezone

from django.db.models import Q, Count, Sum, F, ExpressionWrapper, DecimalField, Value
from datetime import timedelta
from django.db.models.functions import Coalesce
from decimal import Decimal

###### Fonctions de stats ###########

def get_global_vendeurs_stats(request):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if user.is_authenticated and user.is_staff and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER):
            # Utilisez un queryset de base filtré par la licence
            queryset = Vendeur.objects.filter(license=profil_staff.license)

            # Utilisez un agrégat pour calculer toutes les stats en une seule requête
            stats = queryset.aggregate(
                total_vendeurs=Count('id'),
                vendeurs_actifs=Count('id', filter=Q(etat_approbation=True, etat_suppression=False, etat_validation=True)),
                vendeurs_en_attente=Count('id', filter=Q(etat_approbation=False, etat_suppression=False, etat_validation=True)),
                vendeurs_inactifs=Count('id', filter=Q(etat_approbation=True, etat_suppression=False, etat_validation=False)),
                vendeurs_supprimes=Count('id', filter=Q(etat_suppression=True)),
            )
            return stats
    except Exception as e:
        # Il est important de logguer l'erreur pour la détection de bugs
        print(f"Erreur dans get_global_vendeurs_stats : {e}")
        return None
    return None


def get_global_article_stats(request, vendeur_code=None, period='all_time'):
    try:
        user = request.user
        
        # Vérification des permissions
        is_staff_admin = user.is_authenticated and user.is_staff and user.account_profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER)

        if not user.is_authenticated:
            return None

        queryset = Article.objects.filter(etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON)

        # Filtrage basé sur le rôle de l'utilisateur ou le vendeur
        if is_staff_admin:
            queryset = queryset.filter(license=user.account_profil_staff.license)
        elif vendeur_code:
            queryset = queryset.filter(vendeur__code=vendeur_code)
        else:
            # L'utilisateur n'a pas les droits pour voir les stats globales
            return None

        # Filtrage par période
        end_date = timezone.now()
        if period == 'last_30_days':
            start_date = end_date - timedelta(days=30)
            queryset = queryset.filter(date_creation__gte=start_date)
        elif period == 'last_7_days':
            start_date = end_date - timedelta(days=7)
            queryset = queryset.filter(date_creation__gte=start_date)

        stats = queryset.aggregate(
            nombre_articles_total=Count('id'),
            nombre_articles_en_attente_depot=Count('id', filter=Q(statut_traitement=StatutTraitement.EN_ATTENTE_DEPOT)),
            nombre_articles_en_attente_ramassage=Count('id', filter=Q(statut_traitement=StatutTraitement.EN_ATTENTE_RAMASSAGE)),
            nombre_articles_livres=Count('id', filter=Q(statut_traitement__in=array_statut_traitement_livre)),
            nombre_articles_retournes=Count('id', filter=Q(statut_traitement__in=array_statut_traitement_retour)),
            nombre_articles_en_cours=Count('id', filter=Q(statut_traitement__in=array_statut_traitement_en_cours)),
            
            # Statistiques financières
            # Les noms de champs ont été renommés pour éviter les duplications
            montant_valeur_totale_globale=Coalesce(Sum('valeur_totale'), Value(Decimal('0'))),
            montant_valeur_totale_livres=Coalesce(Sum('valeur_totale', filter=Q(statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            
            montant_total_frais_attente=Coalesce(Sum('montant_total_frais', filter=Q(etat_reglement=False, statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_total_frais_regles=Coalesce(Sum('montant_total_frais', filter=Q(etat_reglement=True, statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_frais_total=Coalesce(Sum('montant_total_frais', filter=Q(statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            
            montant_a_reverser_attente=Coalesce(Sum('montant_a_reverser', filter=Q(etat_reversement=False, statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_reverse_effectue=Coalesce(Sum('montant_a_reverser', filter=Q(etat_reversement=True, statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_reversement_total=Coalesce(Sum('montant_a_reverser', filter=Q(statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
        )

        stats['taux_succes'] = (stats.get('nombre_articles_livres', 0) / stats.get('nombre_articles_total', 1)) * 100 if stats.get('nombre_articles_total', 0) > 0 else 0
        return stats
    
    except Exception as e:
        print(f"Erreur dans get_global_article_stats : {e}")
        return None


def get_articles_stats_by_vendeur(request, period='all_time'):
    try:
        user = request.user
        
        # Vérification des permissions
        is_staff_admin = user.is_authenticated and user.is_staff and user.account_profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER)

        if not is_staff_admin:
            return None

        # Créez le queryset de base des vendeurs pour la licence de l'utilisateur
        vendeurs_queryset = Vendeur.objects.filter(license=user.account_profil_staff.license)

        # Ajoutez un filtre de période si nécessaire
        article_filters = Q(vendeur_article__etat_suppression=False) & ~Q(vendeur_article__statut_traitement=StatutTraitement.BROUILLON)

        end_date = timezone.now()
        if period == 'last_30_days':
            start_date = end_date - timedelta(days=30)
            article_filters &= Q(date_creation__gte=start_date)
        elif period == 'last_7_days':
            start_date = end_date - timedelta(days=7)
            article_filters &= Q(date_creation__gte=start_date)

        # Annoter le queryset des vendeurs pour obtenir les statistiques de leurs articles
        stats_by_vendeur = vendeurs_queryset.annotate(
            # Statistiques sur les articles
            nombre_articles_total=Count('vendeur_article', filter=article_filters),
            nombre_articles_en_attente_depot=Count('vendeur_article', filter=article_filters & Q(vendeur_article__statut_traitement=StatutTraitement.EN_ATTENTE_DEPOT)),
            nombre_articles_en_attente_ramassage=Count('vendeur_article', filter=article_filters & Q(vendeur_article__statut_traitement=StatutTraitement.EN_ATTENTE_RAMASSAGE)),
            nombre_articles_livres=Count('vendeur_article', filter=article_filters & Q(vendeur_article__statut_traitement__in=array_statut_traitement_livre)),
            nombre_articles_retournes=Count('vendeur_article', filter=article_filters & Q(vendeur_article__statut_traitement__in=array_statut_traitement_retour)),
            nombre_articles_en_cours=Count('vendeur_article', filter=article_filters & Q(vendeur_article__statut_traitement__in=array_statut_traitement_en_cours)),
            
            # Statistiques financières
            montant_total_frais_attente=Coalesce(Sum('vendeur_article__montant_total_frais', filter=article_filters & Q(vendeur_article__etat_reglement=False, vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_total_frais_regles=Coalesce(Sum('vendeur_article__montant_total_frais', filter=article_filters & Q(vendeur_article__etat_reglement=True, vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_frais_total=Coalesce(Sum('vendeur_article__montant_total_frais', filter=article_filters & Q(vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            
            montant_a_reverser_attente=Coalesce(Sum('vendeur_article__montant_a_reverser', filter=article_filters & Q(vendeur_article__etat_reversement=False, vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_reverse_effectue=Coalesce(Sum('vendeur_article__montant_a_reverser', filter=article_filters & Q(vendeur_article__etat_reversement=True, vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
            montant_reversement_total=Coalesce(Sum('vendeur_article__montant_a_reverser', filter=article_filters & Q(vendeur_article__statut_traitement__in=array_statut_traitement_livre)), Value(Decimal('0'))),
        )

        """
        # Ajoutez le taux de succès après la requête pour éviter les erreurs de division par zéro
        # C'est plus propre de le faire en Python après la requête SQL
        for vendeur in stats_by_vendeur:
            if vendeur.nombre_articles_total > 0:
                vendeur.taux_succes = (vendeur.nombre_articles_livres / vendeur.nombre_articles_total) * 100
            else:
                vendeur.taux_succes = 0
        """

        return stats_by_vendeur
    
    except Exception as e:
        print(f"Erreur dans get_articles_stats_by_vendeur : {e}")
        return None 


def get_top_n_vendeurs(request, n=5, metric='articles'):
    try:
        user = request.user
        profil_staff = user.account_profil_staff

        if not (user.is_authenticated and user.is_staff and profil_staff.role_profil in (TypeProfilStaffChoice.ADMINISTRATEUR, TypeProfilStaffChoice.COMPTABLE, TypeProfilStaffChoice.SUPER)):
            return None

        queryset = Vendeur.objects.filter(license=profil_staff.license, vendeur_article__statut_traitement__in=array_statut_traitement_livre)
        
        queryset = queryset.annotate(
                articles_livres=Count('vendeur_article'),
                valeur_totale=Coalesce(Sum('vendeur_article__valeur_totale'), Value(Decimal('0'))),
                montant_total_frais=Coalesce(Sum('vendeur_article__montant_total_frais'), Value(Decimal('0'))),
            )

        if metric == 'articles':
            # Top vendeurs par nombre d'articles livrés
            return queryset.order_by('-articles_livres')[:n]
        elif metric == 'ca':
            # Top vendeurs par chiffre d'affaires (montant total des frais)
            return queryset.order_by('-montant_total_frais')[:n]
        else:
            return None

    except Exception as e:
        print(f"Erreur dans get_top_n_vendeurs : {e}")
        return None
    
