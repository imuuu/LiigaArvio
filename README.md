# LiigaArvio 1.0

Paikallinen, suomenkielinen sovellus Liigan **runkosarjaotteluiden** tulosten arviointiin. Musta käyttöliittymä, päivän ja huomisen pelit, valittu päivämäärä, tilastot ja laskelmat samassa paikassa.

## Käynnistä Windowsissa

1. Kloonaa repo: `git clone https://github.com/imuuu/LiigaArvio.git` (tai pura ZIP tavalliseen kansioon, mutta silloin automaattipäivitys ei toimi).
2. Koneella pitää olla **Python 3.10 tai uudempi**. Ohjelma ei tarvitse pip-paketteja.
3. Avaa **`KAYNNISTA.bat`**. Sovellus avaa selaimen. Pidä komentorivi-ikkuna auki.

Sulkeminen: **Ctrl+C** käynnistysikkunassa. Selainvälilehden sulkeminen ei yksin pysäytä taustalla toimivaa paikallista palvelinta.

Jos selain ei avaudu, avaa käynnistysikkunassa näkyvä osoite, tavallisesti `http://127.0.0.1:8765`. Varatun portin tilalle kokeillaan automaattisesti seuraavia portteja. Et tarvitse ylläpitäjän oikeuksia, pilvipalvelua, kirjautumista tai API-avainta.

Pythonin virallinen asennussivu: https://www.python.org/downloads/windows/

### Automaattipäivitys

Jokaisella käynnistyksellä sovellus tarkistaa GitHubista (`git fetch`), onko repoon tullut uusia muutoksia. Jos on, ne haetaan (`git merge --ff-only`) ja sovellus käynnistyy uudelleen uudella koodilla. Päivitys ei koskaan estä käynnistystä: jos verkkoa ei ole, git puuttuu tai kansiossa on omia muokkauksia, jotka estäisivät päivityksen, käynnistetään nykyinen versio ja ikkunaan tulostetaan syy.

Päivityksen voi ohittaa valitsimella `--no-update` tai ympäristömuuttujalla `LIIGAARVIO_NO_UPDATE=1`.

Mac/Linux: `python3 app.py` tai `./start.sh`. Päivä ja otteluiden ajat lasketaan **Suomen ajassa**, vaikka koneesi olisi muualla. Windows ilman `tzdata`-pakettia käyttää varajärjestelmänä Suomen EU-kesäaikasääntöä; sitä ei tarvitse asentaa erikseen.

## Tärkeä ero: toteutettu verkkohaku, mutta ei vahvistettua live-koetta

Ohjelma sisältää oikeat Liiga.fi:n JSON-hakukutsut ja niiden vastauksiin perustuvan laskennan. **Liigan live-JSON-vastausta ei kuitenkaan saatu auki rakennusympäristöstä**: Pythonin verkkoyhteys epäonnistui nimenselvitykseen, ja erillinen selainhakutyökalukaan ei pystynyt avaamaan JSON-osoitteita. Siksi verkkohakua ei ole vahvistettu päästä päähän oikealla Liiga-vastauksella.

Parseri on testattu Liigan API:ta käyttävän julkisen ohjelmakoodin kenttärakenteesta laadituilla keinotekoisilla testivastauksilla. Tämä ei korvaa oikean palvelun integraatiotestiä. Julkinen rajapinta voi muuttua tai estää pääsyn. Sovellus ei lupaa datan saatavuutta tai virallista API-tukea.

Koneellasi **`TARKISTA_YHTEYS.bat`** hakee päivän ohjelman ja kauden tulokset sekä tekee saatavilla olevasta ottelusta arvion. Raportti syntyy tiedostoon `yhteystesti.txt`. Jos lähteen rakenne tai pääsy on muuttunut, raportti näyttää virheen. Sovellus ei keksi tilalle numeroita eikä naamioi demoarvoja oikeiksi.

## Käyttö

Valitse **Tänään**, **Huomenna** tai päivämäärä. Vasemmalla näkyvät lähteen palauttamat ottelut. Klikkaa peliä. Jos pelipäivä on tyhjä, saat mahdollisuuksien mukaan painikkeen seuraavaan oikeaan pelipäivään.

**Yhteenveto** näyttää yksittäisen todennäköisimmän lopputuloksen, sen malliprosentin, seuraavat tulosvaihtoehdot, voittajan malliprosentit, 60 minuutin 1/X/2-jakauman, maaliodotuksen ja kauden maalikeskiarvot. Tarkimman yksittäisen tuloksen todennäköisyys on usein pieni; ohjelma näyttää myös kaikkien muiden tulosten yhteisen osuuden.

**Laskelmat** avaa oikeat syöttöluvut ja kaikki vaiheet: taustakeskiarvo, kausitasaus, viimeiset pelit, koti/vieras, keskinäiset, maaliodotukset ja Poisson-kaava. Näytön desimaalit on pyöristetty; laskenta käyttää täyttä liukulukutarkkuutta.

**Otteluhistoria** näyttää viimeiset viisi peliä ja enintään kuusi keskinäistä kohtaamista tältä ja edelliseltä kaudelta. Riveillä näkyvät erikseen lopputulos ja 60 minuutin tulos. Kaikkien käytettyjen tämän kauden pelien listat ovat avattavissa.

**Lähteet** näyttää pyydetyt JSON-osoitteet, hakuajat ja välimuistin tilan. **Tallenna laskelma** lataa JSON-raportin, joka sisältää parametrit, käytettyjen joukkueiden tilastot, kaikki laskentaan kelpuutetut runkosarjaotteluiden rivit, lähdeosoitteet, maaliodotukset ja todennäköisyydet.

**Historiatesti** laskee valittuun päivään mennessä päättyneistä enintään 100 ottelusta jälkikäteen ennusteet ilman saman ottelupäivän tuloksia lähtötiedoissa. Se raportoi tarkan tuloksen, kolmen yleisimmän tuloksen ja suosikin osumat sekä Brier- ja log-loss-pisteytyksen. Se ei säädä painoja tai tee automaattista optimointia.

## Kaksi mallia

**Tasoitettu malli** on oletus. Se käyttää kauden maaleja, edellisen kauden taustaa, viimeisiä viittä peliä, koti-/vieraspelejä ja keskinäisiä. Pieniä otoksia tasataan. Käsin valitut painot on dokumentoitu; mallia ei ole kalibroitu aidolla Liiga-historialla.

**Perusmaalikeskiarvo** on vertailu: kotijoukkueen maaliodotus = (kotijoukkueen tehdyt/ottelu + vierasjoukkueen päästetyt/ottelu) / 2. Vieraille sama toisin päin. Ei koti-/vieraspainotusta, edellisen kauden tasausta tai keskinäisten lisäpainoa. Näin näet myös alkuperäisen yksinkertaisen laskentatavan ilman lisätekijöitä. Molemmat joukkueet tarvitsevat vähintään yhden kelvollisen tämän kauden ottelun.

## Mitä versiosta puuttuu?

Pudotuspelit, CHL, harjoitusottelut, NHL ja muut sarjat eivät kuulu tähän versioon. Kokoonpanoja, aloittavia maalivahteja, loukkaantumisia, matkustamista, lepoa, erikoistilanteita, laukaisudataa ja markkinakertoimia ei haeta eikä huomioida. Ei live-ennusteita: myös jo alkaneelle/pelatulle ottelulle näytetään ennen sen ottelupäivää rajattu arvio.

Laskentaa ei ole opetettu toteutuneilla tuloksilla. Riippumattomat Poisson-maalit ja tasatilanteen 50/50-ratkaisu ovat mallin oletuksia, eivät todistettuja Liiga-totuuksia. Työkalu auttaa vertailemaan lukuja; se ei takaa ennustetarkkuutta tai voittoa.

## Välimuisti ja tietoturva

Liiga-pyynnöt tehdään Python-palvelimesta, joten selaimen CORS-rajoitukset eivät estä niitä. Palvelin kuuntelee vain `127.0.0.1`:ssä, ei lähiverkossa. Sallittu verkkodata tulee vain HTTPS-osoitteista `liiga.fi` ja `www.liiga.fi`; TLS-varmennusta ei poisteta. Sivulla ei ole ulkoisia skriptejä, analytiikkaa tai fonttilatauksia.

Tuoretta dataa säilytetään yleensä viisi minuuttia. Edellisillä kausilla käytetään pidempää välimuistia. **Päivitä**-painikkeessakin on 30 sekunnin pyyntöjarru. Vanha ottelupäivä voidaan pitää välimuistissa vuorokauden; täydellisessä kausivastauksessa päivitysväli on lyhyempi. Jos verkkohaku epäonnistuu ja aiempi oikea vastaus löytyy, se näytetään vanhentuneena hakuajankohtineen. Korjaamattoman vanhan datan pohjalta tehty arvio voi olla puutteellinen.

Windowsin datakansio: `%LOCALAPPDATA%\LiigaArvio\cache`. Muilla järjestelmillä yleensä `~/.cache/liigaarvio`. Välimuistin voi poistaa sovelluksen ollessa suljettuna. Demo ei kirjoita oikean datan välimuistiin.

Paikallista kehityspalvelinta ei ole tarkoitettu julkaistavaksi internetiin.

## Testit ja esittely

`KAYNNISTA_DEMO.bat` / `python app.py --demo` avaa saman käyttöliittymän **selvästi merkityllä, keksityllä testidatalla**. Tämä testaa käyttöä ilman internetiä. Demo ei sisällä oikeita Ilves–TPS-tuloksia eikä sen osumaprosentteja saa tulkita mallin urheilulliseksi suorituskyvyksi.

Automaattiset testit: `python -m unittest discover -s tests -v`.

Tekninen raportti: `TESTIRAPORTTI.md`. Täydet laskentasäännöt: `MALLI_JA_LASKENTA.md`. Rajapintaosoitteet: `DATALAHTEET.md`.

## Tiedostot

- `app.py`: paikallinen HTTP-palvelin ja käynnistys.
- `liigaarvio/provider.py`: verkkohaku, lähdehistoria ja välimuisti.
- `liigaarvio/domain.py`: datan tarkistus, ottelut, aikavyöhyke ja 60 minuutin tulokset.
- `liigaarvio/model.py`: kaikki maalilaskut, jakaumat ja historiatesti.
- `liigaarvio/service.py`: ottelun, historian ja laskennan yhdistäminen.
- `liigaarvio/demo.py`: erillinen keinotekoinen esittelyaineisto.
- `static/`: tumma käyttöliittymä ilman ulkoisia riippuvuuksia.
- `tests/`: automaattiset testit.

Aiemman keskustelun ristiriitaisia kausitilastoja tai tulosarvioita ei käytetä ohjelman lähtödatan lähteenä.
