# Datalähteet ja hakupolku

## Ensisijainen lähde

Liigan oma verkkosivusto: https://liiga.fi/fi/ohjelma

Sovellus ei hae satunnaisia ennusteartikkeleita hakukoneesta. Se pyytää JSON-ottelurivejä ja laskee tilastot itse. Tällä vältetään eri päivien ja kausien sekoittaminen hakutuloksista. Ohjelma ei ole Liigan virallinen sovellus eikä käytölle ole tässä paketissa luvattu palvelutasoa.

## Toteutetut kutsut

Päiväkohtainen ohjelma ja tulokset:

```
https://liiga.fi/api/v2/games?tournament=runkosarja&date=YYYY-MM-DD
```

Koko kauden ensisijainen yritys:

```
https://liiga.fi/api/v2/games?tournament=runkosarja&season=2027
```

Vaihtoehtoiset kausiyritykset:

```
https://liiga.fi/api/v2/schedule?tournament=runkosarja&season=2027
https://liiga.fi/api/v1/games?tournament=runkosarja&season=2027
```

Kausitunniste on kauden loppuvuosi: esimerkin 2027 vastaa kautta 2026–27. Käyttäjän valitsema päivä ratkaisee kauden; sitä ei kovakoodata nykyiseksi vuodeksi.

Jos kausikutsu palauttaa vain päivävastauksen (`previousGameDate` / `nextGameDate`), sitä **ei käytetä koko kautena**. Ohjelma kokeilee kausivaihtoehtoja, ja viimeisenä vaihtoehtona kulkee päivärajapinnan `previousGameDate`-ketjua taaksepäin. Ketjun maksimipituus on 190 ottelupäivää. Katkennut tai tulevaisuuteen kiertävä ketju aiheuttaa virheen; sitä ei väitetä täydelliseksi historiaksi.

Jos otteluohjelman kausivastauksessa on vanhoja pelejä ilman tuloksia, ohjelma pyytää näiden päivien tulokset erikseen. Pelkkä menneisyydessä oleva alkamisaika ei riitä merkitsemään peliä pelatuksi.

## Olennaiset luetut kentät

Ottelusta: `id`, `season`, `start`, `serie` tai `tournament`, `started`, `ended`, `finishedType`, `gameTime`.

Joukkueista: `homeTeam`, `awayTeam`, `teamName` (varalla `name` tai `teamId`:n nimi) ja `goals`.

Päivänavigoinnista: `previousGameDate`, `nextGameDate`.

Tuntemattomia pakollisia kenttiä, puuttuvia maalilukuja ja epäselviä tulostyyppejä ei korvata arvauksilla. Pelien kaksoiskappaleet poistetaan kausi+ID-avaimella. Ristiriitaiset kaksoiskappaleet aiheuttavat virheen.

## Mihin rajapintatutkimus perustui?

Päivärajapinnan käyttö ja keskeiset kentät tarkistettiin julkisen Liiga-asiakasohjelman lähdekoodista:

https://raw.githubusercontent.com/joniok/sm-liiga-rosters/main/app/liiga_client.py

Tarkistetussa toteutuksessa on `LIIGA_API_BASE = https://liiga.fi/api/v2`, päiväkohtainen `/games`-kutsu parametreilla `tournament` ja `date`, sekä `games`, `previousGameDate`, `nextGameDate`, `homeTeam`, `awayTeam`, `teamName`, `goals`, `season`, `start`, `ended` ja `serie` -kenttien käyttöä. Tätä toisen projektin koodia ei ole kopioitu sovelluksen toteutukseksi. Se on rajapinnan käyttötavan lähde, ei palveluntarjoajan virallinen sopimus.

Vanhempi julkinen asiakastoteutus käyttää API v1 -pohjaosoitetta:

https://github.com/dsgkirkby/CanucksArmy/blob/master/liiga_v2.py

Kausikutsuja kokeillaan yhteensopivuuspolkuina; niiden ajantasaista live-vastetta ei ole tässä ympäristössä pystytty vahvistamaan.

## Mitä ei saatu varmistettua?

Rakennusympäristön Python-haku epäonnistui DNS-nimenselvitykseen. Erilliset web-työkalun avausyritykset Liigan JSON-osoitteisiin epäonnistuivat myös. Tästä syystä paketissa ei ole ladattua oikeaa Liiga-kausiaineistoa, ja esikatselukuva näyttää vain keksittyä demodataa.

Ei siis väitetä, että live-integraatio olisi jo testattu onnistuneesti. Omalla koneella `TARKISTA_YHTEYS.bat` tekee tämän tarkistuksen käyttäen samoja varsinaisia hakufunktioita kuin sovellus. Jos API ei ole saatavilla tai muoto on muuttunut, tarvitaan datalähdeadapterin päivitys; ohjelma ei siirry piilossa toiseen tai keksittyyn lähteeseen.

## Tarkistettavuus käytössä

Jokaisen haun URL ja hakuhetki ovat Lähteet-välilehdellä. Sama tieto sekä kaikki laskentaan kelpuutetut ottelurivit sisältyvät tallennettavaan JSON-laskelmaan. Ohjelman välimuistissa säilyy lisäksi alkuperäinen JSON-vastaus. Hakuajankohta ei ole sama asia kuin lähteen lupaama päivitysajankohta.
