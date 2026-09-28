# Malli ja laskenta — versio 1.0.0

Kaikki tässä kuvatut laskut on toteutettu tiedostossa `liigaarvio/model.py`. Tulosten lukeminen ja jatkoajan käsittely ovat tiedostossa `liigaarvio/domain.py`. Painot ovat **käsin valittuja heuristiikkoja**, eivät oikealla Liiga-datalla estimoituja tai kalibroituja parametreja.

## 1. Mitkä ottelut kelpaavat?

Vain Liigan runkosarja. Nykyinen ja edellinen kausi pidetään erillään. Ennustettavan ottelupäivän tai myöhempien päivien tuloksia ei käytetä. Rajaus on aikaisempi seuraavista:

- ottelupäivän alku klo 00.00 Suomen ajassa;
- laskentahetki.

Historiasta kelpuutetaan vain rajaa ennen alkaneet, haettaessa päättyneiksi merkityt ottelut, joille molemmat 60 minuutin maaliluvut pystytään määrittämään. Ennustettavan ottelun oma tunniste suljetaan lisäksi pois. Tämä ei ole live-malli. Huomiselle ei arvata tänään vielä pelaamattomien pelien tuloksia.

Jos loppuaika ei ole lähteessä, historiatesti ei voi täydellisesti rekonstruoida lähteen tietotilaa menneellä hetkellä. Kokonaisen ottelupäivän poisrajaus poistaa saman päivän ottelutulosten vuodon. Historialliset korjaukset voivat silti olla mukana.

## 2. Lopputulos ja 60 minuutin tulos

Tavallisella peliajalla päättyneen ottelun maalit käytetään sellaisenaan.

Jatkoajalla tai voittolaukauksilla ratkenneessa ottelussa virallisen tuloksen voittajalta poistetaan yksi ratkaisumaali. Esimerkiksi **3–2 JA → 2–2 / 60 min**. Muunnos tehdään vain, kun tulostyyppi tunnistetaan ja maalin ero on tasan yksi.

Tuntematonta nimenomaista tulostyyppiä ei arvata. Kun tulostyyppi puuttuu kokonaan, päättyneen ottelun `gameTime == 3600` voi vahvistaa tavallisen peliajan ja `gameTime > 3600` lisäajan. Puuttuva maaliluku ei ole nolla. Peruttu, keskeytetty, luovutettu tai vielä kesken oleva ottelu ei kelpaa.

Sarjan lopputulosmaalit ja 60 minuutin maalit näytetään erikseen. Ennustemallin pohja on 60 minuutin maaleissa. Lopputulosjakaumaan lisätään erillinen ratkaisumaali.

## 3. Perusmaalikeskiarvomalli

Olkoon joukkueen GF = tehdyt 60 minuutin maalit / ottelut ja GA = päästetyt 60 minuutin maalit / ottelut.

```
lambda_koti   = (GF_koti + GA_vieras) / 2
lambda_vieras = (GF_vieras + GA_koti) / 2
```

Perusmallissa ei ole koti-/vieraskorjausta, viime pelien lisäpainoa, keskinäisten lisäpainoa tai edellisen kauden joukkuekohtaista taustatasausta. Keskinäiset silti näytetään historiassa, mutta niiden laskentapaino on nolla. Molemmat tarvitsevat vähintään yhden kelvollisen tämän kauden ottelun.

Tämä on alkuperäisen keskustelun maalikeskiarvoidean toistettava versio. Keskustelun aiempia ristiriitaisia tilastolukuja ei ole kopioitu ohjelmaan.

## 4. Tasoitettu malli

### 4.1 Sarjan taustakeskiarvo

`N` = nykyisen kauden kelvollisten otteluiden määrä koko sarjassa.
`G` = näiden otteluiden koti- ja vierasmaalien yhteissumma, 60 min.
`mu_prev` = edellisen kauden maalit / (2 × ottelumäärä).
`m` = min(30, edellisen kauden ottelumäärä).

```
mu = (G/2 + m × mu_prev) / (N + m)
```

Jos edellinen kausi puuttuu, `mu = G / (2N)`. Jos kummaltakaan kaudelta ei ole yhtään kelvollista peliä, laskenta keskeytetään. Ohjelmassa ei ole piilotettua kovakoodattua "Liigan todellista maalikeskiarvoa".

### 4.2 Joukkuekohtainen pohja

Jos joukkueelta löytyy edellisen kauden otteluita:

```
pohja_GF = (edellisen kauden GF_summa + 10 × mu) / (edellisen kauden ottelut + 10)
pohja_GA = (edellisen kauden GA_summa + 10 × mu) / (edellisen kauden ottelut + 10)
```

Muuten molemmat pohjat ovat `mu`. Nykyistä kautta tasataan kahdeksan pohjaottelun painolla:

```
GF0 = (tämän kauden GF_summa + 8 × pohja_GF) / (tämän kauden ottelut + 8)
GA0 = (tämän kauden GA_summa + 8 × pohja_GA) / (tämän kauden ottelut + 8)
```

Taustan suhteellinen paino pienenee kauden edetessä. Nolla nykyisen kauden peliä näytetään nollana ottelumääränä ja puuttuvana raakakeskiarvona — ei keksittynä joukkueen tilastona.

### 4.3 Viimeiset viisi peliä

Otetaan tämän kauden viimeiset enintään viisi kelvollista ottelua. Niiden raakoja GF/GA-keskiarvoja merkitään `R_GF`, `R_GA`.

```
r = 0,20 × min(viimeisten otteluiden määrä / 5, 1)
GF1 = (1-r) × GF0 + r × R_GF
GA1 = (1-r) × GA0 + r × R_GA
```

Jos pelejä ei ole, r = 0. Näiden pelien sisältyminen myös kausikeskiarvoon on tarkoituksellista lisäpainotusta, ei riippumatonta uutta todistusaineistoa.

### 4.4 Koti-/vieraspelit

Kotijoukkueelle käytetään sen nykyisen kauden kotiotteluita ja vierasjoukkueelle sen vierasotteluita. Näiden GF/GA-keskiarvoja merkitään `V_GF`, `V_GA`.

```
v = 0,20 × min(vastaavan pelipaikan ottelumäärä / 10, 1)
GF2 = (1-v) × GF1 + v × V_GF
GA2 = (1-v) × GA1 + v × V_GA
```

Tämän päälle ei lisätä erillistä, mielivaltaista kotietumaalia. Pelipaikkaluvut sisältävät kuitenkin vastustajaohjelman ja pienen otoksen vaikutuksia; niitä ei ole korjattu vastustajien vahvuuden mukaan.

### 4.5 Vastustajien yhdistäminen

```
lambda_koti0   = (GF2_koti + GA2_vieras) / 2
lambda_vieras0 = (GF2_vieras + GA2_koti) / 2
```

### 4.6 Keskinäiset

Nykyiseltä ja edelliseltä kaudelta valitaan yhteensä enintään kuusi uusinta runkosarjakohtaamista. Kotijoukkueen näkökulmasta niiden tehdyt ja päästetyt 60 minuutin maalit ovat `H_GF` ja `H_GA`. Kohtaamiset saavat saman painon keskinäisen keskiarvon sisällä; vanhan ottelun erillistä ikävaimennusta ei ole.

```
h = 0,10 × min(keskinäisten määrä / 5, 1)
lambda_koti   = (1-h) × lambda_koti0 + h × H_GF
lambda_vieras = (1-h) × lambda_vieras0 + h × H_GA
```

Ei kohtaamisia → h = 0. Yksi kohtaaminen → h = 0,02. Viisi tai kuusi → h = 0,10. Nykyisen ja edellisen kauden kohtaamismäärät eritellään näytöllä.

## 5. Maalijakauma

Kummankin joukkueen maalit oletetaan riippumattomaksi Poisson-muuttujaksi:

```
P(X=k) = exp(-lambda) × lambda^k / k!
P(koti=h, vieras=a) = P_koti(h) × P_vieras(a)
```

Todennäköisyydet lasketaan rekursiivisesti ilman ulkoista matematiikkakirjastoa. Häntä katkaistaan alle 10^-13 massaan per joukkue ja jakauma normalisoidaan. Mallin lopullisille lambdoille on tekninen raja 0,05–15; sen aktivoituminen lisätään varoituksiin. Normaalidatalla alaraja estää täysin nollaisen pienen otoksen absoluuttisen nollatodennäköisyyden.

**Yksittäinen todennäköisin tulos on jakauman suurin alkio, ei keskiarvojen pyöristys.**

60 minuutin jakaumasta:

```
P(1) = summa tilanteista h > a
P(X) = summa tilanteista h = a
P(2) = summa tilanteista h < a
```

## 6. Ottelun lopputulos ja voittaja

Tasatilanteen ratkaisu on **oletuksena 50/50**. Maalivahti- tai erikoistilastot eivät muuta sitä.

Jokaisen tasatuloksen n–n todennäköisyydestä puolet lisätään lopputulokseen (n+1)–n ja puolet n–(n+1). Muut 60 minuutin tulokset säilyvät. Näin lopputulosjakaumaan ei jää tasapelejä.

```
P(kotivoitto lopullisesti) = P(1) + 0,5 × P(X)
P(vierasvoitto lopullisesti) = P(2) + 0,5 × P(X)
E(maalit 60 min) = lambda_koti + lambda_vieras
E(maalit lopputuloksessa) = lambda_koti + lambda_vieras + P(X)
```

Viimeinen odotusarvo laskee viralliseen lopputulokseen kirjautuvan ratkaisumaalin myös voittolaukauksissa. Se ei tarkoita, että jokainen voittolaukaus olisi tavallinen pelimaali.

Maaliväli on kokonaismaalijakauman 10. ja 90. prosenttipisteen välinen kokonaislukuväli. Diskreettiys voi nostaa sen kattavuuden yli 80 prosentin. Kyse on **mallin** jakaumasta, ei kalibroidusta todellisen maailman luottamusvälistä.

## 7. Historiatesti

Enintään 100 valittuun päivään mennessä päättynyttä nykyisen kauden ottelua. Jokaisen kohdalla laskenta tehdään uudelleen vain kyseisen päivän alkua edeltävillä tuloksilla. Ei satunnaista jakoa, ei tulevan kauden valmiita keskiarvoja, ei kohdeottelun omaa tulosta lähtöluvuissa.

Mittarit:

- Tarkka lopputulos ja kolmen suurimman lopputulosvaihtoehdon osuma.
- Mallin suosikin voitto. Täysin tasavahvat tapaukset jätetään tämän nimittäjästä pois.
- Moniluokkainen Brier 60 min 1/X/2: `sum((p_i - y_i)^2)`, asteikko 0–2.
- Log-loss: `-ln(toteutuneen 60 min tulosluokan todennäköisyys)`.

Tasainen 1/3–1/3–1/3-arvaus antaa Brier-arvoksi 2/3. Se on heikko tekninen vertailukohta, ei vahva Liiga-vertailumalli. Testi ei optimoi parametreja. Aikaisemmin julkaistujen ennusteiden todellista etukäteisseurantaa ei tallenneta. Lähteeseen myöhemmin tehdyt korjaukset voivat sisältyä nykyisin haettuun historiaan.

## 8. Mallin rajat

Jääkiekon maalit eivät välttämättä ole riippumattomia tai tasaisesti syntyviä. Pelitilanne, tyhjä maali, jäähyt, kokoonpanot ja vaihtuva pelitapa vaikuttavat. Tämän mallin oletuksia ei ole testattu aidolla Liiga-datalla. Kohtaamishistoria voi vanhentua pelaajavaihdosten takia. Painotetut osajoukot ovat päällekkäisiä.

Työkalun tarkoitus on tehdä yksinkertainen tilastoarvio toistettavasti ja näyttää sen perusteet, ei esittää tutkimuksellisesti validoitua ennustejärjestelmää.
