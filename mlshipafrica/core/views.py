from django.shortcuts import render
from django.shortcuts import redirect, render
from django.urls import reverse
from django_dump_die.middleware import dd

from management.models import Article, Encaissement, HistoriqueArticle, ProfilStaff, ReglementArticle, Reversement, Tarification, Vendeur
from management.forms import ProfilStaffForm, TarificationForm, VendeurColisForm, VendeurForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect

from core.models import AchatLicense, Configuration, FormatArticle, License, Localite, PartenaireLogistique, Zone
from core.forms import ConfigurationForm, FormatArticleForm, LicenseForm, LocaliteForm, PartenaireLogistiqueForm, ZoneForm
from mlshipafrica.enums import StatutTraitement, StatutVendeur, TypeProfilStaffChoice, TypeVendeurChoice
from django.db import transaction
from django.contrib.auth.models import User, Group
from allauth.account.models import EmailAddress


# Create your views here.

@login_required
def _liste(request):
    param = request.GET.get('param', '')
    
    #aucun module selectionné donc erreur 404
    if param == '':
        raise Http404 
    try:
        user = request.user
        profil_staff = user.account_profil_staff
        #statut_traitement = StatutTraitement

        if user.is_authenticated and user.is_staff\
            and profil_staff.role_profil in (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.ADMINISTRATEUR):

            articles = Article.objects.filter(license=profil_staff.license, etat_suppression=False)
            suite_breadcrumb = "" 
            
            if param == "licenses" and profil_staff.role_profil == TypeProfilStaffChoice.SUPER:
                suite_breadcrumb = "Licenses" 
                suite_libelle_nouveau = "License" 
                licenses = License.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")

            if param == "configurations":
                suite_breadcrumb = "Configurations" 
                suite_libelle_nouveau = "Configuration" 
                configurations = Configuration.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")

            if param == "formats_articles":
                suite_breadcrumb = "Formats colis" 
                suite_libelle_nouveau = "Format colis" 
                formats_articles = FormatArticle.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")
                if profil_staff.license:
                    formats_articles = formats_articles.filter(license=profil_staff.license)

            if param == "zones":
                suite_breadcrumb = "Zones" 
                suite_libelle_nouveau = "Zone" 
                zones = Zone.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")
                if profil_staff.license:
                    zones = zones.filter(license=profil_staff.license)

            if param == "localites":
                suite_breadcrumb = "Localités" 
                suite_libelle_nouveau = "Localité" 
                localites = Localite.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")
                if profil_staff.license:
                    localites = localites.filter(license=profil_staff.license)

            if param == "partenaires_logistiques":
                suite_breadcrumb = "Partenaires logistiques" 
                suite_libelle_nouveau = "Partenaire logistique" 
                partenaires_logistiques = PartenaireLogistique.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")
                if profil_staff.license:
                    partenaires_logistiques = partenaires_logistiques.filter(license=profil_staff.license)

            if param == "tarifications":
                suite_breadcrumb = "Tarifications" 
                suite_libelle_nouveau = "Tarification" 
                tarifications = Tarification.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "zone_depart", "zone_arrivee", "format_article", "-date_creation")
                if profil_staff.license:
                    tarifications = tarifications.filter(license=profil_staff.license)

            if param == "profils_staff":
                suite_breadcrumb = "Utilisateurs gestionnaires" 
                suite_libelle_nouveau = "Utilisateur gestionnaire" 
                utilisateurs = ProfilStaff.objects.filter(etat_suppression=False).order_by("-etat_validation", "etat_suppression", "-date_creation")
                if profil_staff.license:
                    utilisateurs = utilisateurs.filter(license=profil_staff.license)



        # historique_articles = HistoriqueArticle.objects.filter(article=article, etat_validation=True, etat_suppression=False).exclude(statut_traitement=StatutTraitement.BROUILLON).order_by("date_creation")
    except Exception as e:
        raise Http404
    return render(request, 'core/_liste.html', locals())


# Create param
@login_required
@transaction.atomic
def _new(request):
    param = request.GET.get('param', '')
    
    #aucun module selectionné donc erreur 404
    if param == '':
        raise Http404 
    try:
        with transaction.atomic():
            user = request.user
            profil_staff = user.account_profil_staff

            if user.is_authenticated and user.is_staff\
                    and profil_staff.role_profil in (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.ADMINISTRATEUR):
                
                if param == "licenses" and profil_staff.role_profil == TypeProfilStaffChoice.SUPER:
                    suite_breadcrumb = "Licenses" 
                    suite_libelle_nouveau = "License" 
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = LicenseForm(data=(request.POST or None), files=(request.FILES or None), instance=License()) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            license = form.save(commit=False)
                            license.save()

                            achat = AchatLicense()
                            achat.license = license
                            achat.debut = request.POST["debut"]
                            achat.fin = request.POST["fin"]
                            achat.cout = request.POST["cout"]
                            achat.save()

                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=licenses") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = LicenseForm(instance=License())

                
                if param == "configurations":
                    suite_breadcrumb = "Configurations" 
                    suite_libelle_nouveau = "Configuration" 
                    init_configuration = Configuration()
                    init_configuration.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ConfigurationForm(data=(request.POST or None), files=(request.FILES or None), instance=init_configuration) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            configuration = form.save(commit=False)
                            if profil_staff.license:
                                configuration.license = profil_staff.license
                            configuration.save()

                            old_configurations = Configuration.objects.filter(license=configuration.license, etat_suppression=False, etat_validation=True).exclude(pk=configuration.pk)
                            for old_configuration in old_configurations:
                                old_configuration.etat_validation = False
                                old_configuration.save()

                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=configurations") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ConfigurationForm(instance=init_configuration)

                
                if param == "formats_articles":
                    suite_breadcrumb = "Formats colis" 
                    suite_libelle_nouveau = "Format colis" 
                    init_format_article = FormatArticle()
                    init_format_article.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = FormatArticleForm(data=(request.POST or None), files=(request.FILES or None), instance=init_format_article) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            format_article = form.save(commit=False)
                            format_article.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                format_article.license = profil_staff.license
                            format_article.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=formats_articles") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = FormatArticleForm(instance=init_format_article)


                if param == "zones":
                    suite_breadcrumb = "Zones" 
                    suite_libelle_nouveau = "Zone" 
                    init_zone = Zone()
                    init_zone.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ZoneForm(data=(request.POST or None), files=(request.FILES or None), instance=init_zone) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            zone = form.save(commit=False)
                            zone.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                zone.license = profil_staff.license
                            zone.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=zones") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ZoneForm(instance=init_zone)


                if param == "localites":
                    suite_breadcrumb = "Localités" 
                    suite_libelle_nouveau = "Localité" 
                    init_localite = Localite()
                    init_localite.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = LocaliteForm(data=(request.POST or None), files=(request.FILES or None), instance=init_localite) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            localite = form.save(commit=False)
                            localite.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                localite.license = profil_staff.license
                            localite.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=localites") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = LocaliteForm(instance=init_localite)


                if param == "partenaires_logistiques":
                    suite_breadcrumb = "Partenaires logistiques" 
                    suite_libelle_nouveau = "Partenaire logistique" 
                    init_partenaire_logistique = PartenaireLogistique()
                    init_partenaire_logistique.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = PartenaireLogistiqueForm(data=(request.POST or None), files=(request.FILES or None), instance=init_partenaire_logistique) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            partenaire_logistique = form.save(commit=False)
                            partenaire_logistique.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                partenaire_logistique.license = profil_staff.license
                            partenaire_logistique.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=partenaires_logistiques") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = PartenaireLogistiqueForm(instance=init_partenaire_logistique)


                if param == "tarifications":
                    suite_breadcrumb = "Tarifications" 
                    suite_libelle_nouveau = "Tarification" 
                    init_tarification = Tarification()
                    init_tarification.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = TarificationForm(data=(request.POST or None), files=(request.FILES or None), instance=init_tarification) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            tarification = form.save(commit=False)
                            tarification.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                tarification.license = profil_staff.license
                            tarification.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=tarifications") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = TarificationForm(instance=init_tarification)


                if param == "profils_staff":
                    suite_breadcrumb = "Utilisateurs gestionnaires" 
                    suite_libelle_nouveau = "Utilisateur gestionnaire" 
                    init_utilisateur = ProfilStaff()
                    init_utilisateur.license = profil_staff.license
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ProfilStaffForm(data=(request.POST or None), files=(request.FILES or None), instance=init_utilisateur) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            utilisateur = form.save(commit=False)
                            utilisateur.etat_validation = request.POST["statut"]
                            
                            new_user = User()
                            new_user.username = utilisateur.email
                            new_user.email = utilisateur.email
                            new_user.last_name = request.POST["last_name"]
                            new_user.first_name = request.POST["first_name"]
                            new_user.is_staff = True
                            new_user.set_password(request.POST['password'])
                            new_user.save()
                            
                            is_group_exist = Group.objects.filter(name=utilisateur.role_profil).exists()
                            if is_group_exist == False:
                                Group.objects.create(name=utilisateur.role_profil)
                            group = Group.objects.get(name=utilisateur.role_profil)
                        
                            new_user.groups.add(group)
                            new_user.save()

                            email = EmailAddress.objects.create(
                                email=utilisateur.email,
                                verified=True,
                                primary=True,
                                user=new_user,
                            )
                            email.save()
                            
                            if profil_staff.license:
                                utilisateur.license = profil_staff.license
                            utilisateur.user = new_user
                            utilisateur.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=profils_staff") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ProfilStaffForm(instance=init_utilisateur)


                return render(request, 'core/_new.html', locals())
            
    except Exception as e:
        raise Http404
    return redirect('index')


# Create param
@login_required
@transaction.atomic
def _edit(request, code):
    param = request.GET.get('param', '')
    
    #aucun module selectionné donc erreur 404
    if param == '':
        raise Http404 
    try:
        with transaction.atomic():
            user = request.user
            profil_staff = user.account_profil_staff

            if user.is_authenticated and user.is_staff\
                    and profil_staff.role_profil in (TypeProfilStaffChoice.SUPER, TypeProfilStaffChoice.ADMINISTRATEUR):
                

                if param == "licenses" and profil_staff.role_profil == TypeProfilStaffChoice.SUPER:
                    suite_breadcrumb = "Licenses" 
                    suite_libelle_nouveau = "License" 
                    license = License.objects.get(code=code)
                    achat_licenses = AchatLicense.objects.filter(license=license, etat_suppression=False).order_by("fin")
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = LicenseForm(data=(request.POST or None), files=(request.FILES or None), instance=license) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            if "submit_annuler_achat_license" in request.POST and request.POST["submit_annuler_achat_license"]:
                                if str(license.get_achat_license_last().pk) == request.POST["last_achat_license"]:
                                    achat = license.get_achat_license_last()
                                    achat.etat_suppression = True
                                    achat.save()
                            else:
                                license = form.save(commit=False)
                                license.etat_validation = request.POST["license_statut"]
                                license.save()

                                if license.get_achat_license_last():
                                    achat = license.get_achat_license_last()
                                    achat.debut = request.POST["debut_old"]
                                    achat.fin = request.POST["fin_old"] if request.POST["fin_old"] else None
                                    achat.cout = request.POST["cout_old"] if request.POST["cout_old"] else achat.cout
                                    achat.save()

                                if request.POST["debut_new"] and request.POST["debut_new"] is not None and request.POST["debut_new"] != ""\
                                and request.POST["cout_new"] and request.POST["cout_new"] is not None and request.POST["cout_new"] != "":
                                    new_achat = AchatLicense()
                                    new_achat.license = license
                                    new_achat.debut = request.POST["debut_new"]
                                    new_achat.fin = request.POST["fin_new"] if request.POST["fin_new"] else None
                                    new_achat.cout = request.POST["cout_new"]
                                    new_achat.save()

                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=licenses") 


                if param == "configurations":
                    suite_breadcrumb = "Configurations" 
                    suite_libelle_nouveau = "Configuration"
                    configuration = Configuration.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ConfigurationForm(data=(request.POST or None), files=(request.FILES or None), instance=configuration) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            configuration = form.save(commit=False)
                            configuration_clone = configuration
                            configuration_clone.pk = None 
                            configuration_clone.save()
                            
                            old_configurations = Configuration.objects.filter(license=configuration_clone.license, etat_suppression=False, etat_validation=True).exclude(pk=configuration_clone.pk)
                            for old_configuration in old_configurations:
                                old_configuration.etat_validation = False
                                old_configuration.save()

                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=configurations") 
                        
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ConfigurationForm(instance=configuration)


                if param == "formats_articles":
                    suite_breadcrumb = "Formats colis" 
                    suite_libelle_nouveau = "Format colis"
                    format_article = FormatArticle.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = FormatArticleForm(data=(request.POST or None), files=(request.FILES or None), instance=format_article) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            format_article = form.save(commit=False)
                            format_article.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                format_article.license = profil_staff.license
                            format_article.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=formats_articles") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = FormatArticleForm(instance=format_article)


                if param == "zones":
                    suite_breadcrumb = "Zones" 
                    suite_libelle_nouveau = "Zone"
                    zone = Zone.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ZoneForm(data=(request.POST or None), files=(request.FILES or None), instance=zone) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            zone = form.save(commit=False)
                            zone.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                zone.license = profil_staff.license
                            zone.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=zones") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ZoneForm(instance=zone)


                if param == "localites":
                    suite_breadcrumb = "Localités" 
                    suite_libelle_nouveau = "Localité"
                    localite = Localite.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = LocaliteForm(data=(request.POST or None), files=(request.FILES or None), instance=localite) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            localite = form.save(commit=False)
                            localite.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                localite.license = profil_staff.license
                            localite.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=localites") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = LocaliteForm(instance=localite)


                if param == "partenaires_logistiques":
                    suite_breadcrumb = "Partenaires logistiques" 
                    suite_libelle_nouveau = "Partenaire logistique"
                    partenaire_logistique = PartenaireLogistique.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = PartenaireLogistiqueForm(data=(request.POST or None), files=(request.FILES or None), instance=partenaire_logistique) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            partenaire_logistique = form.save(commit=False)
                            partenaire_logistique.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                partenaire_logistique.license = profil_staff.license
                            partenaire_logistique.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=partenaires_logistiques") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = PartenaireLogistiqueForm(instance=partenaire_logistique)


                if param == "tarifications":
                    suite_breadcrumb = "Tarifications" 
                    suite_libelle_nouveau = "Tarification"
                    tarification = Tarification.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = TarificationForm(data=(request.POST or None), files=(request.FILES or None), instance=tarification) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            tarification = form.save(commit=False)
                            tarification.etat_validation = request.POST["statut"]
                            if profil_staff.license:
                                tarification.license = profil_staff.license
                            tarification.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=tarifications") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = TarificationForm(instance=tarification)


                if param == "profils_staff":
                    suite_breadcrumb = "Utilisateurs gestionnaires" 
                    suite_libelle_nouveau = "Utilisateur gestionnaire"
                    utilisateur = ProfilStaff.objects.get(code=code)
                    if request.method == 'POST': # S'il s'agit d'une requête POST
                        form = ProfilStaffForm(data=(request.POST or None), files=(request.FILES or None), instance=utilisateur) # Nous reprenons les donnée
                        #print(form)
                        if form.is_valid(): # Nous vérifions que les données envoyées sont valides
                            utilisateur = form.save(commit=False)
                            utilisateur.etat_validation = request.POST["statut"]
                            
                            cureent_user = User()
                            utilisateur.user.username = utilisateur.email
                            utilisateur.user.email = utilisateur.email
                            utilisateur.user.last_name = request.POST["last_name"]
                            utilisateur.user.first_name = request.POST["first_name"]
                            if request.POST['password'] and request.POST['password'] != "" and request.POST['password'] is not None:
                                utilisateur.user.set_password(request.POST['password'])
                            utilisateur.user.save()
                            
                            is_group_exist = Group.objects.filter(name=utilisateur.role_profil).exists()
                            if is_group_exist == False:
                                Group.objects.create(name=utilisateur.role_profil)
                            group = Group.objects.get(name=utilisateur.role_profil)
                        
                            if group not in utilisateur.user.groups.all():
                                utilisateur.user.groups.add(group)
                                utilisateur.user.save()

                            is_email_exist = EmailAddress.objects.filter(email=utilisateur.email, user=utilisateur.user).exists()
                            if is_email_exist == False:
                                email = EmailAddress.objects.create(
                                    email=utilisateur.email,
                                    verified=True,
                                    primary=True,
                                    user=utilisateur.user,
                                )
                                email.save()
                            
                            if profil_staff.license:
                                utilisateur.license = profil_staff.license
                            utilisateur.save()
                            return HttpResponseRedirect(reverse('core:core_liste')+"?param=profils_staff") 
                    else: # Si ce n'est pas du POST, c'est probablement une requête     GET
                        form = ProfilStaffForm(instance=utilisateur)


                return render(request, 'core/_edit.html', locals())

    except Exception as e:
        raise Http404

    return redirect('index')

