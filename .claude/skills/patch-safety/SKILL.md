---
name: patch-safety
description: >
  Use when modifying ChannelOS source files programmatically (Python patch scripts
  that edit main.py, publisher.py, client.py, etc. via str.replace / pathlib). Enforces
  unique-anchor matching, exact-string "already patched" guards, dead-code checks after
  block replacement, and mandatory grep+compile+dry-run verification before any costly run.
  Trigger on: editing pipeline source, applying a patch script, str_replace, "déjà patché"
  conditions, anything before a render/publish that consumes credits.
---

# Édition de code sûre — ChannelOS

## Avant tout render/run coûteux : grep
Le bug n°1 récurrent = édition non appliquée. Toujours vérifier la présence de la modif
AVANT de lancer un render (qui consomme des crédits JSON2Video) :
```bash
grep -n "marqueur_unique_de_la_modif" channelos/main.py   # doit retourner la/les ligne(s)
python3 -m py_compile channelos/main.py && echo "syntaxe OK"
```

## Conditions « déjà patché » : tester la chaîne EXACTE
Faux positif classique : tester un mot-clé qui existe ailleurs.
```python
# MAUVAIS — "COALESCE" existe dans une autre requête → faux "déjà patché"
if "COALESCE" in src: ...
# BON — tester la chaîne complète réellement insérée
if "published_at=COALESCE(%s, NOW())" in src: ...
```

## Ancrer sur un contexte UNIQUE
`src.replace(old, new, 1)` frappe la **1re** occurrence. Si l'ancre apparaît plusieurs fois,
mauvaise cible. Ancrer sur plusieurs lignes de contexte unique, jamais une ligne seule
qui se répète (ex. l'appel `publish(...)` existait en 2 endroits → patché au mauvais).

## Après remplacement d'un bloc : chasser le code mort
Remplacer un bloc peut laisser la queue de l'ancienne version, qui s'exécute à la place :
```python
        return channels[idx]      # nouvelle logique
        row = cur.fetchone()      # ZOMBIE de l'ancienne version
    return row[0] if row else None  # c'est CELUI-CI qui tourne → bug
```
Toujours `sed -n` la fonction entière après patch pour confirmer qu'elle finit proprement.

## Un patch qui échoue ne doit RIEN écrire
```python
ok = True
if anchor not in src:
    print("❌ ancre introuvable"); ok = False
...
if ok:
    p.write_text(src)   # écriture SEULEMENT si tout est vert
else:
    print("⚠️ RIEN écrit")
```

## Heredocs : préférer /tmp rejouables
Les heredocs collés dans le terminal se tronquent au collage. Pour tout test non trivial,
écrire un fichier `/tmp/test_*.py` qu'on relance proprement, plutôt qu'un `python3 -c "..."`
multiligne fragile.

## Séquence de validation type (zéro crédit)
```bash
python3 -m py_compile channelos/main.py && echo "syntaxe OK"
grep -n "marqueur" channelos/main.py                 # présence
python3 -m channelos "AI tools" --no-render          # dry-run jusqu'au B-roll, 0 crédit
```
Le test doit pouvoir ÉCHOUER de façon informative (assert sur la valeur attendue) —
un test qui passe toujours ne teste rien.