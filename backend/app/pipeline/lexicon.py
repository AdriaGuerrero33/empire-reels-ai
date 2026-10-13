"""Marcadores retóricos por idioma (es / ca / en).

Son una señal más entre varias (prosodia, estructura, confianza, coherencia
temática, LLM opcional): ninguna decisión editorial depende solo de ellos.
"""
from __future__ import annotations

STOP = {
    "es": set("""a al algo algunos ante antes aquí así aunque bien cada como con contra cual cuando de del
        desde donde dos el ella ellas ellos en entre era eran es esa esas ese eso esos esta estaba estamos
        estar estas este esto estos estoy fue fueron ha había han hasta hay la las le les lo los más me mi
        mis mucho muy nada ni no nos nosotros o os otra otro para pero poco por porque que qué se sea ser
        si sí sin sobre son su sus también tan te tener tengo ti tiene tienen todo todos tu tus un una uno
        unos vamos va van vez y ya yo hacer hace hacen puede pueden cosa cosas entonces pues bueno vale
        decir digo dice muy gente ahora aquí ahí allí estar está están creo""".split()),
    "ca": set("""a al als algun alguna amb aquest aquesta aquests això allò així als com de del dels des
        el ella ells els em en entre era és es eren està estan fa fan fer han ha hi i jo la les li lo me
        mes més molt no nosaltres o per perquè però poc que què se si sí sense sobre són sóc també tan te
        tenir tinc tot tots tu un una uns va van vaig doncs bé ara aquí llavors cosa coses diu dir""".split()),
    "en": set("""a about after all also am an and any are as at be because been but by can could did do
        does doing don't for from get got had has have he her here him his how i if in into is it its
        it's just like me more most my no not now of on one or our out so some than that the their them
        then there these they this those to too up us very was we were what when where which who why
        will with would you your you're thing things really gonna going""".split()),
}

MARKERS = {
    "question": {
        "es": ["¿", "qué", "cómo", "por qué", "cuánto", "cuál", "sabías", "te has preguntado", "imagina"],
        "ca": ["què", "com", "per què", "quant", "quin", "sabies", "imagina"],
        "en": ["what", "how", "why", "did you know", "have you ever", "imagine", "ever wonder"],
    },
    "surprise": {
        "es": ["pero", "sin embargo", "en realidad", "la verdad", "nadie", "nunca", "increíble", "sorprend",
               "resulta que", "de repente", "lo que nadie", "secreto", "error", "mito", "jamás", "de hecho"],
        "ca": ["però", "en realitat", "la veritat", "ningú", "mai", "increïble", "sorprèn", "resulta que",
               "de sobte", "secret", "error", "mite", "de fet"],
        "en": ["but", "however", "actually", "the truth", "nobody", "never", "incredible", "surpris",
               "turns out", "suddenly", "secret", "mistake", "myth", "in fact"],
    },
    "tip": {
        "es": ["tienes que", "debes", "hay que", "el truco", "la clave", "consejo", "no hagas", "evita",
               "prueba", "haz", "empieza", "deja de", "recuerda", "fíjate", "paso", "primero", "segundo"],
        "ca": ["has de", "cal", "el truc", "la clau", "consell", "no facis", "evita", "prova", "fes",
               "comença", "deixa de", "recorda", "pas", "primer", "segon"],
        "en": ["you should", "you need to", "you have to", "the key", "tip", "don't", "avoid", "try",
               "start", "stop", "remember", "step", "first", "second"],
    },
    "anecdote": {
        "es": ["cuando yo", "un día", "una vez", "me pasó", "recuerdo", "hace años", "mi primer",
               "mi primera", "conocí", "estaba", "empecé", "me dijo", "cuando era"],
        "ca": ["quan jo", "un dia", "una vegada", "em va passar", "recordo", "fa anys", "el meu primer",
               "la meva primera", "vaig conèixer", "vaig començar", "em va dir"],
        "en": ["when i", "one day", "once", "happened to me", "i remember", "years ago", "my first",
               "i met", "i was", "i started", "told me"],
    },
    "explanation": {
        "es": ["porque", "significa", "es decir", "por ejemplo", "funciona", "la razón", "esto hace",
               "por eso", "lo que pasa"],
        "ca": ["perquè", "significa", "és a dir", "per exemple", "funciona", "la raó", "per això"],
        "en": ["because", "means", "for example", "works", "the reason", "that's why", "which is"],
    },
    "cta": {
        "es": ["sígueme", "síguenos", "suscríbete", "comenta", "escríbeme", "escríbenos", "link", "enlace",
               "descarga", "reserva", "llámanos", "visita", "pide", "contacta", "comparte", "guarda este",
               "apúntate", "en la bio"],
        "ca": ["segueix-me", "segueix-nos", "subscriu-te", "comenta", "escriu-me", "enllaç", "descarrega",
               "reserva", "truca'ns", "visita", "contacta", "comparteix", "desa aquest"],
        "en": ["follow", "subscribe", "comment", "link in", "dm me", "message me", "download", "book",
               "call us", "visit", "sign up", "share this", "save this"],
    },
    "problem": {
        "es": ["problema", "pierden", "perder", "pérdida", "error", "fallo", "difícil", "cuesta", "no funciona",
               "sin", "tiempo perdido", "manual", "caos", "estrés", "nadie te", "frustr", "miedo"],
        "ca": ["problema", "perden", "perdre", "pèrdua", "error", "difícil", "costa", "no funciona", "sense",
               "manual", "caos", "estrès", "frustr", "por"],
        "en": ["problem", "lose", "losing", "waste", "mistake", "fail", "hard", "struggle", "doesn't work",
               "without", "manual", "chaos", "stress", "frustrat", "fear"],
    },
    "solution": {
        "es": ["solución", "la forma", "puedes", "automatiz", "sistema", "método", "herramienta", "así es",
               "la manera", "lo que hacemos", "te ayuda", "resuelve"],
        "ca": ["solució", "la forma", "pots", "automatitz", "sistema", "mètode", "eina", "la manera", "t'ajuda"],
        "en": ["solution", "here's how", "the way", "you can", "automat", "system", "method", "tool", "helps"],
    },
    "benefit": {
        "es": ["ahorra", "ahorrar", "ganar", "ganas", "resultado", "conseguir", "multiplica", "más clientes",
               "más ventas", "rentable", "libertad", "crecer", "facturar", "beneficio"],
        "ca": ["estalvia", "estalviar", "guanyar", "resultat", "aconseguir", "multiplica", "més clients",
               "més vendes", "rendible", "créixer", "benefici"],
        "en": ["save", "gain", "result", "achieve", "multiply", "more clients", "more sales", "profit",
               "grow", "freedom", "revenue", "benefit"],
    },
    "emphatic": {
        "es": ["el mejor", "el peor", "lo más", "todo", "nada", "siempre", "nunca", "absolutamente", "brutal",
               "importante", "clave", "literalmente", "cien por cien"],
        "ca": ["el millor", "el pitjor", "el més", "tot", "res", "sempre", "mai", "absolutament", "brutal",
               "important", "clau", "literalment"],
        "en": ["the best", "the worst", "the most", "everything", "nothing", "always", "never", "absolutely",
               "huge", "important", "key", "literally"],
    },
    "closure": {
        "es": ["por eso", "así que", "en resumen", "al final", "en definitiva", "la conclusión", "y punto",
               "eso es todo", "lo importante"],
        "ca": ["per això", "així que", "en resum", "al final", "en definitiva", "la conclusió"],
        "en": ["so that's", "that's why", "in short", "in the end", "bottom line", "the takeaway", "that's it"],
    },
    "humor": {
        "es": ["jaja", "jajaja", "broma", "risa", "gracioso", "locura", "flipas", "qué fuerte", "madre mía",
               "en serio"],
        "ca": ["haha", "broma", "riure", "divertit", "bogeria", "flipes", "mare meva", "de debò"],
        "en": ["haha", "lol", "joke", "funny", "crazy", "seriously", "oh my god", "insane"],
    },
}

# Conectores que indican que la frase depende de la anterior (resta autonomía).
LEADING_CONNECTORS = {
    "es": ["y", "pero", "entonces", "porque", "o", "que", "pues", "además", "también", "esto", "eso",
           "aquello", "ahí", "luego"],
    "ca": ["i", "però", "llavors", "perquè", "o", "que", "doncs", "a més", "també", "això", "allò"],
    "en": ["and", "but", "so", "because", "or", "that", "this", "also", "then", "which"],
}

NUMBER_WORDS = {
    "es": ["uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "cien",
           "mil", "millón", "millones", "doble", "triple", "mitad", "por ciento"],
    "ca": ["un", "dos", "tres", "quatre", "cinc", "sis", "set", "vuit", "nou", "deu", "cent", "mil",
           "milió", "milions", "doble", "triple", "meitat", "per cent"],
    "en": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred",
           "thousand", "million", "millions", "double", "triple", "half", "percent"],
}


def lang_key(lang: str) -> str:
    return lang if lang in ("es", "ca", "en") else "es"
