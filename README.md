# Erasmus+ · IC Pescara 6

Sito statico (HTML, CSS e JS vanilla) pubblicato su GitHub Pages:
<https://profdorazio.github.io/erasmus-programme/>

## Struttura

```
index.html            home con tutte le mobilità      (generato)
404.html              pagina di errore                (generato)
<città>/index.html    pagina della mobilità           (generato)
<città>/photos/       foto della galleria (01.jpg, 02.jpg…) + thumbs/
<città>/people/       foto delle testimonianze
<città>/video.mp4     video (facoltativo) + poster.jpg
assets/css/style.css  stile unico
assets/js/main.js     menu, filtri, galleria/lightbox
assets/img/           loghi, favicon, immagine di anteprima social
redirect/             vecchi link di reindirizzamento (generati)
src/mobilities.json   TUTTI i contenuti: testi, date, testimonianze
tools/build.py        genera le pagine e ottimizza le immagini
```

Le pagine HTML sono generate: **non modificarle a mano**. Modifica
`src/mobilities.json` (o CSS e JS) e poi rigenera il sito.

## Rigenerare il sito

```bash
pip install pillow            # una volta sola
python3 tools/build.py
```

Lo script ridimensiona le foto a max 2000px, crea le miniature, estrae il
poster dei video (serve `ffmpeg`) e riscrive tutte le pagine, il sitemap e i redirect.

## Aggiungere una nuova mobilità

1. Crea la cartella `nomecitta/photos/` e copiaci le foto (`01.jpg`, `02.jpg`, …:
   l'ordine dei nomi è l'ordine nella galleria). Vanno bene anche gli originali dal telefono.
2. Facoltativo: `nomecitta/video.mp4` e le foto delle persone in `nomecitta/people/`.
3. Aggiungi un blocco in `src/mobilities.json` copiando uno già esistente
   (`slug` = nome della cartella; `type` = `group`, `shadowing`, `course` o `staff`;
   `cover` = la foto di copertina).
4. Lancia `python3 tools/build.py`, poi fai commit e push.

**Stessa città più volte** (es. Elche 2025 e 2026): usa uno slug diverso
(`elche-2026`) e lo stesso `city`. Il build se ne accorge da solo: aggiunge l'anno
al nome ovunque ("Elche 2025" / "Elche 2026") e collega tra loro le pagine.

Se gli avatar delle testimonianze sono illustrazioni (non foto), aggiungi
`"avatars": "illustration"` alla mobilità: verranno mostrati interi, senza ritaglio.

Design by 11 studio.
