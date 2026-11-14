PERÄMERI-SEURANTA v1.0 – FMI-LIVEHAKU, ASENNETTAVA WEB-SOVELLUS

Sisältö:
- Pietarsaari Leppäluoto (FMISID 134250) ja Raahe Lapaluoto (100540), merivedenkorkeus, mm
- Tankar (FMISID 101661), sää
- Hollihaka: FMI-asematunnusta ei ole vahvistettu. Sovellus ei keksi havaintoja.
  Jos oikea FMISID löytyy, aseta HOLLIHAKA_FMISID ympäristömuuttujaksi.
- Automaattinen 10 minuutin välein tapahtuva päivitys ja 48 tunnin merivedenkorkeuskäyrä.
- Virhetilanteet näytetään, ei keksittyjä arvoja.

KÄYNNISTYS:
1. Asenna Python 3.10 tai uudempi.
2. Avaa komentorivi tämän kansion sisällä.
3. Suorita: python server.py
4. Avaa tietokoneella: http://localhost:8000

PUHELIMELLA:
Palvelin on julkaistava HTTPS-osoitteeseen, jotta sovelluksen voi asentaa
Androidin aloitusnäytölle. Tämä ZIP ei itsessään ole Androidin APK.
Esim. Render/Railway/VPS, käynnistyskomento: python server.py
PORT luetaan ympäristömuuttujasta.
PWA-manifestissa ei ole vielä asennuskuvakkeita; selaimen asennettavuus riippuu selaimesta.

RAJOITUKSET:
- FMI:n livevastauksia ei ole voitu testata tässä ympäristössä. Koodi on toimiva
  toteutuspohja, mutta kenttänimet/parametrit saattavat vaatia korjauksia.
- Merivedenkorkeuden yksikkö on FMI:n WFS:n mm; ei muuteta korkeusjärjestelmää.
- Hollihaka voi olla muun ylläpitäjän sääasema, eikä sen tietoja silloin löydy FMI WFS:stä.
- Sovellus hakee FMI:n avoimia havaintoja, ei ennusteita eikä aallonkorkeutta.
- FMI WFS: https://opendata.fmi.fi/wfs
- FMI avoin data: CC BY 4.0, Ilmatieteen laitos.
