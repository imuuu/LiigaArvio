# Testiraportti — 28.9.2026

## Automaattiset testit

Komento: `python -m unittest discover -s tests -v`

**52 testiä, kaikki läpi.** Ajo Linuxissa, Python 3.13.5. Viimeisimmän ajon kesto noin 0,57 sekuntia; tämä ei ole lupaus verkkohakujen nopeudesta.

Testatut asiat:

- Suomen päivä, kesä-/talviaika ja Windowsin ilman tzdata-pakettia toimiva varareitti.
- Tavallisen peliajan, jatkoajan ja voittolaukausten tulokset.
- Puuttuvat, virheelliset, perutut, keskeneräiset ja tuntemattomat tulokset.
- Otteluiden kaksoiskappaleet, kausirajaus ja runkosarjan erottelu.
- Perusmallin lasku tunnetuilla keksityillä lähtöluvuilla: lambda_koti 2,75 ja lambda_vieras 1,50.
- Poisson-jakauman tunnetut arvot ja todennäköisyysmassan summa.
- Jatkoajan 50/50-jako ja lopputulosjakauman tasapelittömyys.
- Ennustettavan ottelun, saman päivän ja tulevien tulosten poisrajaus.
- Pienen keskinäisen otoksen paino ja puuttuvan historian käsittely.
- Vanha välimuisti verkkovirheen aikana; ei automaattista siirtymistä demodataan.
- Päiväkohtaisen vastauksen erottaminen koko kaudesta ja katkeavan historiaketjun virhe.
- Paikallisen HTTP-palvelimen käyttö, demo-API:n päästä päähän -laskenta, Host/Origin-suojaukset ja staattisten polkujen rajaus.

## Käyttöliittymä

Chromium/Playwright-testi keksityllä demodatalla:

- Yhteenveto ja tulosjakauma latautuvat.
- Laskelmat-, Otteluhistoria- ja Lähteet-välilehdet aukeavat.
- JSON-laskelman tallennus käynnistää tiedoston latauksen.
- Historiatesti valmistuu.
- Huomenna-valinta, laskentamallin vaihtaminen, tyhjän päivän näyttö ja seuraava pelipäivä toimivat.
- Mobiilikoko 390 × 844: ei koko sivun vaakasuuntaista ylivuotoa.
- JavaScriptin ajonaikaisia virheitä: **0**.

Tämän ympäristön hallittu Chromium esti suoran navigoinnin localhostiin (`ERR_BLOCKED_BY_ADMINISTRATOR`). Käyttöliittymän testissä HTML/CSS/JS ladattiin siksi selaimen DOM:iin testiohjelmalla ja sen API-kutsut ohjattiin testisillan kautta oikealle paikalliselle HTTP-palvelimelle. Testi käyttää samoja käyttöliittymätiedostoja ja samaa Python-palvelinta, mutta se ei ole käyttäjän Windows-selaimen tavanomaisen käynnistyspolun vahvistus. HTTP-rajapinta testattiin erikseen suoraan paikallisilla HTTP-pyynnöillä.

Esikatselukuva `ESIKATSE_DEMO.png` on tämän sovelluksen todellinen selaimesta otettu kuva. Sen ottelu- ja ennustetiedot ovat keinotekoisia ja kuva on merkitty demoksi.

## Verkkotesti — EI LÄPI

Komento: `python app.py --check --cache-dir ...`

Todellinen vastaus tässä ympäristössä:

```
YHTEYSTESTI EPÄONNISTUI:
Verkkoyhteys Liigaan epäonnistui: [Errno -3] Temporary failure in name resolution
```

Myös erilliset web-työkalun avausyritykset Liiga.fi:n JSON-osoitteisiin epäonnistuivat. **Yhtään oikeaa kauden JSON-vastausta ei tässä rakennuksessa saatu.** Datan muotoa ja hakutapaa selvitettiin rajapintaa käyttävästä julkisesta lähdekoodista; parseritestit käyttävät keinotekoisia, vastaavaa rakennetta noudattavia testitietoja.

Siksi ei väitetä, että nykyinen Liiga-live-integraatio olisi testattu toimivaksi. Se on toteutettu, mutta edellyttää onnistunutta yhteystestiä käyttäjän koneelta ja voi vaatia adapterin päivityksen, jos rajapinta eroaa tutkitusta käyttötavasta.

## Muut rajat

Windowsin `.bat`-käynnistimiä ei ole ajettu Windowsissa. Niissä käytetään tavanomaisia `py -3` / `python` -kutsuja ja version tarkistusta. Python-koodi on tarkistettu myös Python 3.10 -syntaksitasolla.

Mallin oikeaa ennustetarkkuutta ei ole mitattu Liigan toteutuneilla tuloksilla. Demotestin osumaprosentit ovat ohjelmistotestin tuloksia eivätkä näyttöä urheilutulosten ennustuskyvystä.
