# -*- coding: utf-8 -*-
"""Grille officielle ML COD Intérieur (validée par la direction le 29/10/2026).

- Zones 2 à 6, même numérotation que le partenaire logistique. Abidjan (zone 1) n'est pas desservie.
- Délais en jours ouvrés après l'expédition.
- TARIFS_ML : prix facturés au vendeur, en F CFA (Petit / Moyen). Le format Grand n'est pas encore ouvert.
"""

DELAIS = {2: (2, 3), 3: (3, 4), 4: (3, 4), 5: (3, 4), 6: (3, 4)}

TARIFS_ML = {
    2: {'Petit': 3234, 'Moyen': 4851},
    3: {'Petit': 3481, 'Moyen': 4998},
    4: {'Petit': 3501, 'Moyen': 5032},
    5: {'Petit': 3445, 'Moyen': 5310},
    6: {'Petit': 4321, 'Moyen': 6091},
}

# Coûts partenaire : volontairement ABSENTS du code (le dépôt ne doit jamais contenir de donnée interne).
# Ils se chargent avec --couts /chemin/hors-depot/couts_partenaire.json, ou se saisissent par le CEO
# dans Paramètres › Tarifications. Format du fichier : {"2": {"Petit": 0, "Moyen": 0}, "3": {...}, ...}

LOCALITES = {
    2: [
        'Adiaké', 'Agboville', 'Alépé', 'Assinie', 'Azaguié', 'Bonoua', 'Dabou', 'Grand-Bassam',
        'Jacqueville', 'Kofikro', 'N’Djem', 'Sikensi', 'Toukouzou', 'Toupah',
    ],
    3: [
        'Abengourou', 'Aboisso', 'Agnibilékrou', 'Assouba', 'Baba', 'Bondoukou', 'Bouaflé', 'Bouaké',
        'Daloa', 'Daoukro', 'Divo', 'Duékoué', 'Gagnoa', 'Guiglo', 'Korhogo', 'Man', 'Ouangolodougou',
        'San-Pedro', 'Séguéla', 'Soubré', 'Yamoussoukro', 'Zouan-Hounien',
    ],
    4: [
        '4 Carrefours', 'Adaou', 'Adzopé', 'Affery', 'Agou', 'Ahougnan', 'Fatou', 'Akoboissué', 'Akoupé',
        'Aniassué', 'Appoisso', 'Apprompronou', 'Arrah', 'Ayamé', 'Bayota', 'Belleville', 'Bettié',
        'Bocanda', 'Bonaouin', 'Bongouanou', 'Braffedon', 'Dagadji', 'Dakpadou', 'Dassioko', 'Dibou',
        'Dimbokro', 'Djekanou', 'Ebilassokro', 'Ebounou', 'Fresco', 'Grand-Lahou', 'Grand-Yapo', 'Guitry',
        'Hermankono', 'Hiré', 'Irobo', 'Kanblesso', 'Konanblekro', 'Kongobo', 'Kononfla', 'Kossou', 'Kotobi',
        'Krokrom', 'Lahou-Kpanda', 'Lakota', 'Liliyo', 'M’Batto', 'Maféré', 'N’Douci', 'N’Zianouan',
        'N’Zikro', 'Oumé', 'Oupoyo', 'Ouragahio', 'Pauly-Brousse', 'Péhé', 'Rubino', 'Sahoua', 'Sassandra',
        'Tankessé', 'Tiassalé', 'Tiébissou', 'Tiédo', 'Tiéviessou', 'Toumodi', 'Yakassé-Attobrou',
        'Yakassémé', 'Yaokro', 'Yaou', 'Yocoboué', 'Zikisso',
    ],
    5: [
        'Adjaméné', 'Ahouanou', 'Akakro', 'Akekro', 'Amoriakro', 'Assounvoué', 'Attiékro', 'Bacanda',
        'Bazra-Nattis', 'Bédiala', 'Béoumi', 'Bonon', 'Boron', 'Botro', 'Buyo', 'Dabouyo', 'Diabo',
        'Diatéké', 'Didiévi', 'Diédrou', 'Diégonefla', 'Djebonoua', 'Domaine SOGB', 'Duffrébo',
        'Ferkessedougou', 'Galébouo', 'Gbalagoua', 'Gbogouhé', 'Gonaté', 'Gouméré', 'Grand-Béréby',
        'Grand-Zattry', 'Groussikro', 'Guéhiebly', 'Guépahouo', 'Guessabo', 'Gueyo', 'Guiberoua', 'Issia',
        'Kanzra', 'Katiola', 'Kétro-Bassam', 'Kongaso', 'Koun-Fao', 'Kpouèbo', 'Laoudi-Ba', 'Larabia',
        'M’Bahiakro', 'Manzanouan', 'Massala', 'Méagui', 'Méo', 'Moussadougou', 'Néko', 'Niablé', 'Odiénné',
        'Ogoudou', 'Okrouyo', 'Ouellé', 'Prikro', 'Roc Oulidié', 'Saioua', 'Sakassou', 'Samo', 'Sandégué',
        'Seydougou', 'Sinfra', 'Tabagne', 'Tanda', 'Thoui', 'Tié N’Diékro', 'Tiéningboué', 'Vavoua',
        'Walebo', 'Yabayo', 'Zoukougbeu', 'Zuénoula',
    ],
    6: [
        'Angagui', 'Assuéfry', 'Bagohouo', 'Bangolo', 'Bassawa', 'Biankouman', 'Bilimono', 'Blolequin',
        'Bonahouin', 'Booko', 'Borotou', 'Bouko', 'Bouna', 'Boundiali', 'Dabakala', 'Damanasso', 'Danané',
        'Dianra', 'Diarabana', 'Diawala', 'Dikodougou', 'Djatokro', 'Djiboroso', 'Djouroutou', 'Dobré',
        'Dogbo', 'Doropo', 'Facobly', 'Flakiedougou', 'Gabiadji', 'Gagny', 'Gbakayo', 'Gbapleu', 'Glibiadji',
        'Grabo', 'Guézon', 'Guintéguéla', 'Kani', 'Kanoroba', 'Kasséré', 'Konédougou', 'Kong', 'Koro',
        'Kouassi-Datèkro', 'Kouibly', 'Kouto', 'Liboli', 'Logoualé', 'M’Bengué', 'Madinani', 'Mahapleu',
        'Maninian', 'Mankono', 'Minignan', 'Morityedougou', 'Morondo', 'Nandibo II', 'Napiéolédougou',
        'Néka', 'Niakara', 'Nianda', 'Niapidou', 'Niéllé', 'Ouangolo', 'Ouaninou', 'Petit Bouna',
        'Sagboya V6', 'Samatiguila', 'Sangouiné', 'Sémien', 'Sinématiali', 'Sipilou', 'Sirasso', 'Tabou',
        'Tafiré', 'Taï', 'Tamabo', 'Tamabo Dongbo', 'Tingréla', 'Tongon', 'Tortiya', 'Touba', 'Toulépleu',
        'Transua', 'Varalé', 'Watté', 'Yuala', 'Zagné', 'Zagoréta Gadouan', 'Zamblékro', 'Zéaglo',
    ],
}

