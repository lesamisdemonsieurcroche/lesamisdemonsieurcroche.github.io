"""Génère la section « Écrits » du site à partir de l'export WordPress (WXR).

Usage : python3 build_ecrits.py <export.xml> <dossier_du_site>
"""
import html
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup, Comment

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

# Ordre d'affichage des catégories sur la page « Écrits »
CATEGORIES = [
    ("Lettres & écrits de compositeurs", "lettres", "Correspondances et textes de compositeurs."),
    ("Critiques d'époque", "critiques", "Ce que la presse disait des chefs-d’œuvre… à leur création."),
    ("Chroniques & réflexions", "chroniques", "Réflexions sur la musique et l’art, anecdotes et énigmes."),
    ("Concerts & Salons", "concerts", "Programmes et souvenirs des salons des Amis de Monsieur Croche."),
    ("Vidéos", "videos", "Interprétations filmées."),
]

ATTRS_OK = {"a": ["href"], "img": ["src", "alt"], "iframe": ["src", "title", "allow", "allowfullscreen", "loading"],
            "sup": [], "sub": []}


def slugify(texte):
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:70].strip("-")


def date_fr(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def youtube_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([\w-]{11})", url)
    return m.group(1) if m else None


def nettoyer(contenu):
    """Transforme le HTML WordPress (blocs Gutenberg) en HTML simple et propre."""
    soup = BeautifulSoup(contenu, "html.parser")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in soup.find_all(["script", "style", "noscript"]):
        t.decompose()

    # Vidéos intégrées : l'URL YouTube nue dans un bloc « embed » devient un lecteur
    for fig in soup.find_all("figure"):
        classes = " ".join(fig.get("class", []))
        if "wp-block-embed" in classes:
            vid = youtube_id(fig.get_text())
            if vid:
                div = soup.new_tag("div", attrs={"class": "video"})
                iframe = soup.new_tag("iframe", src=f"https://www.youtube-nocookie.com/embed/{vid}",
                                      title="Vidéo", loading="lazy",
                                      allow="accelerometer; encrypted-media; gyroscope; picture-in-picture")
                iframe["allowfullscreen"] = ""
                div.append(iframe)
                fig.replace_with(div)
            else:
                fig.decompose()
    # URL YouTube seule dans un paragraphe
    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        if re.fullmatch(r"https?://(www\.)?(youtube\.com|youtu\.be)\S+", txt):
            vid = youtube_id(txt)
            if vid:
                div = soup.new_tag("div", attrs={"class": "video"})
                iframe = soup.new_tag("iframe", src=f"https://www.youtube-nocookie.com/embed/{vid}",
                                      title="Vidéo", loading="lazy")
                iframe["allowfullscreen"] = ""
                div.append(iframe)
                p.replace_with(div)

    # Nettoyage des attributs
    for tag in soup.find_all(True):
        if tag.name == "div" and "video" in tag.get("class", []):
            continue
        garder = ATTRS_OK.get(tag.name, [])
        for attr in list(tag.attrs):
            if attr not in garder:
                del tag[attr]
        if tag.name == "img" and tag.get("src", "").startswith("http://"):
            tag["src"] = "https://" + tag["src"][7:]
        if tag.name == "img":
            tag["loading"] = "lazy"
            tag.attrs.setdefault("alt", "")
        if tag.name == "a" and tag.get("href", "").startswith("http"):
            tag["rel"] = "noopener"

    # Supprimer les conteneurs inutiles et les paragraphes vides
    for t in soup.find_all(["span", "div"]):
        if t.name == "div" and "video" in (t.get("class") or []):
            continue
        t.unwrap()
    for p in soup.find_all("p"):
        if not p.get_text(strip=True).replace("\xa0", "") and not p.find("img"):
            p.decompose()
    sortie = str(soup).strip()
    sortie = re.sub(r"\n{3,}", "\n\n", sortie)
    return sortie


def resume(html_propre, n=170):
    texte = BeautifulSoup(html_propre, "html.parser").get_text(" ", strip=True)
    texte = re.sub(r"\s+", " ", texte)
    if len(texte) <= n:
        return texte
    return texte[:n].rsplit(" ", 1)[0] + "…"


def gabarit(titre, description, corps, prefixe="", actuel=""):
    def lien(href, texte, cle):
        cur = ' aria-current="page"' if cle == actuel else ""
        return f'<li><a href="{prefixe}{href}"{cur}>{texte}</a></li>'
    nav = "\n        ".join([
        lien("index.html", "Accueil", "accueil"),
        lien("cours.html", "Cours de piano", "cours"),
        lien("index.html#salons", "Salons", "salons"),
        lien("index.html#lectures", "Lectures", "lectures"),
        lien("index.html#videos", "Vidéos", "videos"),
        lien("ecrits.html", "Écrits", "ecrits"),
        lien("a-propos.html", "À propos", "apropos"),
        '<li><a href="#contact">Contact</a></li>',
    ])
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(titre)} – Les Amis de Monsieur Croche</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,400;0,700;1,400&family=Playfair+Display:ital@0;1&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{prefixe}assets/style.css">
</head>
<body>

  <header class="site-header">
    <a class="site-title" href="{prefixe}index.html">Les Amis de Monsieur Croche</a>
    <p class="site-tagline">Salons musicaux, cours de piano &amp; lectures – Montpellier</p>
    <nav class="site-nav" aria-label="Menu principal">
      <ul>
        {nav}
      </ul>
    </nav>
  </header>

  <main>
{corps}
  </main>

  <footer class="site-footer" id="contact">
    <p class="site-title">Les Amis de Monsieur Croche</p>
    <p>Charles Cabral – pianiste, musicologue et professeur · Montpellier, Port Marianne</p>
    <p><a href="mailto:lesamisdemonsieurcroche@gmail.com">lesamisdemonsieurcroche@gmail.com</a></p>
    <p><a href="https://www.youtube.com/@cabralcharlespianiste9965">YouTube – Charles Cabral, piano</a> · <a href="https://www.youtube.com/@charlescabral1159">YouTube – Un renard sous les étoiles</a> · <a href="https://www.instagram.com/cabralcharles9/">Instagram</a> · <a href="https://www.facebook.com/lesamisdemonsieurcroche/">Facebook</a></p>
  </footer>

</body>
</html>
"""


def main(export, site):
    site = Path(site)
    (site / "ecrits").mkdir(exist_ok=True)
    racine = ET.parse(export).getroot().find("channel")
    articles = []
    for it in racine.findall("item"):
        if it.find("wp:post_type", NS).text != "post" or it.find("wp:status", NS).text != "publish":
            continue
        titre = html.unescape(it.find("title").text or "").strip()
        cats = [html.unescape(c.text) for c in it.findall("category") if c.get("domain") == "category"]
        slug = it.find("wp:post_name", NS).text or ""
        if not slug or slug.isdigit():
            slug = slugify(titre)
        corps = nettoyer(it.find("content:encoded", NS).text or "")
        articles.append({
            "titre": titre, "slug": slugify(slug), "date": it.find("wp:post_date", NS).text[:10],
            "cat": cats[0] if cats else "Chroniques & réflexions", "html": corps, "resume": resume(corps),
        })

    # Une page par article
    for a in articles:
        meme_cat = [b for b in articles if b["cat"] == a["cat"] and b is not a]
        voir_aussi = "".join(f'<li><a href="{b["slug"]}.html">{html.escape(b["titre"])}</a></li>' for b in meme_cat[:5])
        cat_ancre = next((c[1] for c in CATEGORIES if c[0] == a["cat"]), "")
        corps = f"""    <article class="prose article">
      <p class="fil"><a href="../ecrits.html">Écrits</a> › <a href="../ecrits.html#{cat_ancre}">{html.escape(a["cat"])}</a></p>
      <h1>{html.escape(a["titre"])}</h1>
      <p class="date">{date_fr(a["date"])}</p>
      <div class="contenu">
{a["html"]}
      </div>
      {"<aside class='voir-aussi'><h2>Dans la même rubrique</h2><ul class='liste'>" + voir_aussi + "</ul></aside>" if voir_aussi else ""}
      <p><a href="../ecrits.html">← Tous les écrits</a></p>
    </article>"""
        (site / "ecrits" / f'{a["slug"]}.html').write_text(
            gabarit(a["titre"], a["resume"], corps, prefixe="../", actuel="ecrits"), encoding="utf-8")

    # Page index « Écrits »
    blocs = []
    for nom, ancre, intro in CATEGORIES:
        liste = sorted((a for a in articles if a["cat"] == nom), key=lambda a: a["date"], reverse=True)
        if not liste:
            continue
        items = "\n".join(
            f'''        <li>
          <a class="titre-article" href="ecrits/{a["slug"]}.html">{html.escape(a["titre"])}</a>
          <span class="date">{date_fr(a["date"])}</span>
          <p>{html.escape(a["resume"])}</p>
        </li>''' for a in liste)
        blocs.append(f'''      <section id="{ancre}">
        <h2>{html.escape(nom)}</h2>
        <p class="intro-rubrique">{intro}</p>
        <ul class="liste-articles">
{items}
        </ul>
      </section>''')
    sommaire = " · ".join(f'<a href="#{a}">{html.escape(n)}</a>' for n, a, _ in CATEGORIES
                          if any(x["cat"] == n for x in articles))
    corps = f"""    <div class="prose">
      <h1 style="margin-top:3rem">Écrits</h1>
      <p class="lead-ecrits">Lettres de compositeurs, critiques d’époque, chroniques et souvenirs de concerts&nbsp;: la musique racontée.</p>
      <p class="sommaire">{sommaire}</p>
{chr(10).join(blocs)}
    </div>"""
    (site / "ecrits.html").write_text(
        gabarit("Écrits", "Lettres de compositeurs, critiques d'époque, chroniques musicales et souvenirs de concerts, par Les Amis de Monsieur Croche.",
                corps, actuel="ecrits"), encoding="utf-8")
    return articles


if __name__ == "__main__":
    arts = main(sys.argv[1], sys.argv[2])
    print(len(arts), "articles générés")
    for a in arts:
        print(f'  ecrits/{a["slug"]}.html  [{a["cat"]}]  {a["titre"]}')
