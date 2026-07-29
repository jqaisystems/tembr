"""Situation-matched recording scripts (register-matching: a zero-shot clone
inherits the energy of its reference, so people record in the register they
intend to generate in). Every script ends with the spoken consent line.

Structure: SCRIPTS[situation][language] -> {"title", "direction", "lines"}
"""

CONSENT = {
    "en": "This recording is my voice, and I consent to using it for my own voice profile.",
    "pt": "Esta gravação é a minha voz, e autorizo o seu uso no meu perfil de voz.",
}

SCRIPTS = {
    "reference": {
        "label": "Master reference (90s, recommended)",
        "en": {
            "title": "Master voice reference",
            "direction": (
                "The one to record first: about ninety seconds covering the full "
                "range of English sounds. Read at the pace and warmth you want the "
                "clone to speak, because it copies your delivery, not just your "
                "timbre. Breathe between paragraphs. Do not perform, just talk."
            ),
            "lines": [
                "I am recording this so the system can learn my voice, and I am "
                "reading it the way I want that voice to sound: unhurried, warm, "
                "and clear.",
                "Most good work starts the same way: a quiet room, a blank page, "
                "and a question worth answering.",
                "Some days that means choosing a typeface. Some days it means "
                "teaching a machine to do something useful. Both jobs reward "
                "patience.",
                "Let me count, because numbers come up often: one, two, three, "
                "four, five, six, seven, eight, nine, ten. Thirty, sixty, ninety. "
                "Two thousand and twenty six.",
                "Would it be useful if the whole thing ran on your own machine, "
                "with nothing ever leaving the building? That question is worth "
                "sitting with.",
                "There is real pleasure in shipping something finished. I am a "
                "poor judge of my own work until it is out in the world, and then "
                "the usual thing happens: I change one detail, then another, then "
                "I make myself stop.",
                "Good work is just choices, made slowly and defended later. The "
                "rest is patience, and a room quiet enough to hear yourself think.",
                "If it sounds like me here, it will sound like me everywhere else. "
                "So this is the take that matters.",
            ],
        },
        "pt": {
            "title": "Gravação de referência",
            "direction": (
                "A primeira a gravar: cerca de noventa segundos que cobrem toda a "
                "gama de sons do português. Leia ao ritmo e com a calma que quer "
                "ouvir do clone, porque ele copia a sua entrega, não apenas o seu "
                "timbre. Respire entre parágrafos. Não represente, fale."
            ),
            "lines": [
                "Estou a gravar isto para o sistema aprender a minha voz, e leio ao "
                "ritmo e com a calma que quero ouvir de volta.",
                "Quase todo o bom trabalho começa da mesma maneira: uma sala "
                "silenciosa, uma folha em branco e uma pergunta que vale a pena "
                "responder.",
                "Há dias em que isso significa escolher um tipo de letra. Noutros, "
                "significa ensinar uma máquina a fazer algo útil. Os dois exigem "
                "paciência, e aprendi isso com a minha mãe.",
                "Deixem-me contar, porque os números aparecem muitas vezes: um, "
                "dois, três, quatro, cinco, seis, sete, oito, nove, dez. Trinta, "
                "sessenta, noventa. Dois mil e vinte e seis.",
                "E se tudo corresse na sua própria máquina, sem nada sair do "
                "edifício? Há boas razões para pensar nisso amanhã.",
                "Há um prazer verdadeiro em terminar alguma coisa. Por exemplo, sou "
                "mau juiz do meu próprio trabalho até ele estar cá fora, e depois "
                "acontece sempre o mesmo: mudo um pormenor, depois outro, e "
                "obrigo-me a parar.",
                "O bom trabalho são apenas escolhas, feitas devagar e defendidas "
                "mais tarde. O resto é paciência, e uma sala suficientemente calma "
                "para nos ouvirmos pensar.",
                "Se aqui soar a mim, vai soar a mim no próximo trabalho e em todos "
                "os outros. Por isso é esta a gravação que conta.",
            ],
        },
    },
    "casual": {
        "label": "Casual / personal messages",
        "en": {
            "title": "Casual voice notes",
            "direction": "Like a voice message to a friend: relaxed, smiling, unhurried.",
            "lines": [
                "Hey! I just saw your message. That's honestly such good news.",
                "So I was thinking, maybe we grab a coffee this week and catch up properly?",
                "It's been a crazy few days, but in a good way, you know?",
                "Anyway, let me know what works for you. Talk soon!",
            ],
        },
        "pt": {
            "title": "Mensagens casuais",
            "direction": "Como uma mensagem de voz para um amigo: descontraído, a sorrir, sem pressa.",
            "lines": [
                "Olá! Acabei de ver a tua mensagem. Que boa notícia, a sério.",
                "Estava a pensar, e se fôssemos tomar um café esta semana para pôr a conversa em dia?",
                "Têm sido uns dias agitados, mas no bom sentido, sabes?",
                "Diz-me o que dá jeito para ti. Falamos em breve!",
            ],
        },
    },
    "sales": {
        "label": "Sales & outreach",
        "en": {
            "title": "Outreach voice notes",
            "direction": "Warm and confident, like a friendly first call with a prospect, energetic but never pushy.",
            "lines": [
                "Hi Sarah, I came across your company this week and honestly, I was impressed.",
                "I work with teams like yours to save hours every single week: real, measurable time.",
                "Would it be crazy to grab fifteen minutes this Thursday? I think you'll like what you see.",
                "Either way, keep doing what you're doing, it's working.",
            ],
        },
        "pt": {
            "title": "Notas de voz para prospeção",
            "direction": "Caloroso e confiante, como uma primeira chamada simpática com um potencial cliente, com energia mas sem pressionar.",
            "lines": [
                "Olá Marta, encontrei a vossa empresa esta semana e, sinceramente, fiquei impressionado.",
                "Trabalho com equipas como a vossa para poupar horas todas as semanas: tempo real e mensurável.",
                "Seria estranho marcarmos quinze minutos esta quinta-feira? Acho que vai gostar do que vai ver.",
                "De qualquer forma, continuem o bom trabalho. Está a resultar.",
            ],
        },
    },
    "support": {
        "label": "Customer support",
        "en": {
            "title": "Support & reassurance",
            "direction": "Calm, clear and patient: the voice of someone who has solved this problem a hundred times.",
            "lines": [
                "Thanks for reaching out. I've looked into it, and the good news is it's a quick fix.",
                "First, open your settings and find the account section, right at the top.",
                "If anything looks different on your side, don't worry. That's completely normal.",
                "And if you get stuck at any point, just reply here. I'm happy to walk you through it.",
            ],
        },
        "pt": {
            "title": "Apoio ao cliente",
            "direction": "Calmo, claro e paciente: a voz de quem já resolveu este problema cem vezes.",
            "lines": [
                "Obrigado pelo contacto. Já verifiquei, e a boa notícia é que tem solução rápida.",
                "Primeiro, abra as definições e procure a secção de conta, logo no topo.",
                "Se algo parecer diferente do seu lado, não se preocupe. É completamente normal.",
                "E se ficar com dúvidas em algum passo, responda por aqui. Terei todo o gosto em ajudar.",
            ],
        },
    },
    "narration": {
        "label": "Narration & explainer",
        "en": {
            "title": "Narration",
            "direction": "Steady podcast pace with deliberate pauses. Let each sentence land before the next.",
            "lines": [
                "Every great system starts with a simple question: what are we really trying to solve?",
                "In the next few minutes, we'll break this down, step by step.",
                "Some of it will surprise you. Some of it, you already suspected.",
                "By the end, you'll see the whole picture, and how the pieces fit together.",
            ],
        },
        "pt": {
            "title": "Narração",
            "direction": "Ritmo constante de podcast, com pausas deliberadas. Deixe cada frase assentar antes da seguinte.",
            "lines": [
                "Todos os grandes sistemas começam com uma pergunta simples: o que estamos mesmo a tentar resolver?",
                "Nos próximos minutos, vamos analisar isto passo a passo.",
                "Algumas partes vão surpreendê-lo. Outras, já suspeitava.",
                "No final, verá o quadro completo, e como as peças encaixam umas nas outras.",
            ],
        },
    },
    "formal": {
        "label": "Formal & announcements",
        "en": {
            "title": "Formal announcements",
            "direction": "Composed and articulate, like presenting to a board: measured pace, full sentences.",
            "lines": [
                "Good morning, and thank you all for being here today.",
                "Over the past quarter, our results have exceeded every projection we set.",
                "This achievement belongs to the entire team, and I want to recognise that clearly.",
                "Looking ahead, our priorities remain focused, ambitious, and within reach.",
            ],
        },
        "pt": {
            "title": "Anúncios formais",
            "direction": "Sereno e articulado, como numa apresentação à administração: ritmo medido, frases completas.",
            "lines": [
                "Bom dia, e obrigado a todos por estarem aqui presentes.",
                "Ao longo do último trimestre, os nossos resultados superaram todas as projeções definidas.",
                "Esta conquista pertence a toda a equipa, e quero reconhecê-lo claramente.",
                "Olhando em frente, as nossas prioridades continuam focadas, ambiciosas e ao nosso alcance.",
            ],
        },
    },
}


SCRIPTS["energetic"] = {
    "label": "Ads & high energy",
    "en": {
        "title": "High energy read",
        "direction": "Full drive, like the last ten seconds of a radio spot: forward, bright, smiling, never shouting.",
        "lines": [
            "Right, listen, because this part actually matters.",
            "Everything you have been doing by hand? Gone. In the time it takes to read this.",
            "No catch, no subscription, no waiting list. You just start.",
            "So go on, press the button. I will wait right here.",
        ],
    },
    "pt": {
        "title": "Leitura com energia",
        "direction": "Com toda a força, como os últimos dez segundos de um anúncio de rádio: para a frente, brilhante, a sorrir, mas sem gritar.",
        "lines": [
            "Ouça bem, porque esta parte interessa mesmo.",
            "Tudo o que andava a fazer à mão? Acabou. No tempo que leva a ler isto.",
            "Sem truques, sem assinaturas, sem lista de espera. Começa e pronto.",
            "Vá lá, carregue no botão. Eu espero aqui.",
        ],
    },
}

SCRIPTS["audiobook"] = {
    "label": "Audiobook & long reads",
    "en": {
        "title": "Audiobook narration",
        "direction": "Low, unhurried, one long line at a time: the voice you would want reading to you at the end of a long day.",
        "lines": [
            "The house had been quiet for so long that the sound of the door surprised even the dust.",
            "She stood in the hallway with her coat still on, listening to a silence that had changed shape.",
            "Later she would say she knew, in that moment, exactly what had happened. It was not quite true, but it was close enough.",
            "Outside, the rain kept on, patient and uninterested, the way rain always is.",
        ],
    },
    "pt": {
        "title": "Narração de audiolivro",
        "direction": "Grave, sem pressa, uma frase longa de cada vez: a voz que gostaria de ouvir ao fim de um dia comprido.",
        "lines": [
            "A casa estava calada havia tanto tempo que o som da porta surpreendeu até o pó.",
            "Ela ficou no corredor, ainda de casaco vestido, a ouvir um silêncio que tinha mudado de forma.",
            "Mais tarde diria que soube, naquele instante, exatamente o que tinha acontecido. Não era bem verdade, mas era quase.",
            "Lá fora, a chuva continuava, paciente e desinteressada, como a chuva sempre é.",
        ],
    },
}


# What makes a reference script work, written so a stranger cloning their own
# voice in their own language can build one instead of copying ours.
GUIDE = {
    "en": {
        "title": "Write your own reference script",
        "checklist": [
            "150 to 220 words, which lands near 90 seconds at a calm pace. Longer "
            "reads drift in tone and give the model inconsistent material.",
            "Write sentences you would actually say. A natural read clones better "
            "than a phonetic drill, because the model copies your delivery.",
            "Cover the awkward consonant families of your language, the ones a word "
            "list usually skips. In English that is the soft consonants in "
            "'pleasure', 'judge' and 'change', and both kinds of 'th'.",
            "Include a run of numbers. They appear constantly in real use and they "
            "are easy to get wrong.",
            "Include one question, so the clone has a rising intonation to copy and "
            "can ask something without sounding flat.",
            "Change register on the last line. One flat colour throughout gives you "
            "a clone with no range.",
            "Read at the pace and warmth you want back. This is the single biggest "
            "lever you have, and it costs nothing.",
            "One continuous take, 60 to 90 seconds, with natural pauses between "
            "paragraphs.",
            "Do not denoise before you record. Record somewhere quiet instead. The "
            "studio measures the take and offers a cleanup afterwards, and it shows "
            "you what that cleanup costs.",
        ],
        "prompt": (
            "Write a voice cloning reference script in {language}.\n\n"
            "Requirements:\n"
            "- 150 to 220 words, about 90 seconds read at a calm pace.\n"
            "- Eight short paragraphs, each one or two sentences.\n"
            "- Sentences a real person would say out loud, not tongue twisters.\n"
            "- Between them, cover the full sound range of {language}: the awkward "
            "consonant clusters, the nasal or unusual vowels, and any sound "
            "foreign speakers find hard.\n"
            "- One paragraph must be a run of counted numbers.\n"
            "- One paragraph must be a question, so the reader produces a rising "
            "intonation.\n"
            "- The last paragraph should shift register slightly, warmer or firmer, "
            "to give the clone some range.\n"
            "- Neutral first person. No names, no places, nothing that identifies "
            "anyone.\n\n"
            "About the speaker, so the words sound like them: {about you}\n\n"
            "Return only the eight paragraphs, one per line, with no numbering, no "
            "headings and no commentary."
        ),
    },
    "pt": {
        "title": "Escreva a sua própria gravação de referência",
        "checklist": [
            "150 a 220 palavras, o que dá cerca de noventa segundos a um ritmo "
            "calmo. Leituras mais longas mudam de tom e dão ao modelo material "
            "inconsistente.",
            "Escreva frases que diria mesmo. Uma leitura natural clona melhor do "
            "que um exercício fonético, porque o modelo copia a sua entrega.",
            "Cubra os sons difíceis da sua língua. Em português: os nasais (ão, ãe, "
            "õe), o lh e o nh, o r inicial e o rr, os quatro valores do x, e as "
            "vogais abertas contra as fechadas.",
            "Inclua uma série de números. Aparecem sempre no uso real e são fáceis "
            "de estragar.",
            "Inclua uma pergunta, para o clone ter uma entoação ascendente para "
            "copiar e poder perguntar algo sem soar monocórdico.",
            "Mude de registo na última linha. Uma cor só ao longo de tudo dá um "
            "clone sem alcance.",
            "Leia ao ritmo e com a calma que quer ouvir de volta. É a maior "
            "alavanca que tem e não custa nada.",
            "Uma gravação contínua, de 60 a 90 segundos, com pausas naturais entre "
            "parágrafos.",
            "Não limpe o ruído antes de gravar. Grave antes num sítio silencioso. O "
            "estúdio mede a gravação e propõe a limpeza depois, mostrando o que "
            "essa limpeza custa.",
        ],
        "prompt": (
            "Escreva um guião de referência para clonagem de voz em {language}.\n\n"
            "Requisitos:\n"
            "- 150 a 220 palavras, cerca de noventa segundos a um ritmo calmo.\n"
            "- Oito parágrafos curtos, cada um com uma ou duas frases.\n"
            "- Frases que uma pessoa real diria em voz alta, sem trava-línguas.\n"
            "- No conjunto, cubra toda a gama de sons de {language}: os grupos "
            "consonânticos difíceis, as vogais nasais ou pouco comuns, e os sons "
            "que os estrangeiros erram.\n"
            "- Um parágrafo tem de ser uma série de números contados.\n"
            "- Um parágrafo tem de ser uma pergunta, para produzir entoação "
            "ascendente.\n"
            "- O último parágrafo deve mudar ligeiramente de registo, mais caloroso "
            "ou mais firme, para dar alcance ao clone.\n"
            "- Primeira pessoa neutra. Sem nomes, sem lugares, sem nada que "
            "identifique alguém.\n\n"
            "Sobre quem vai ler, para as palavras soarem a essa pessoa: {about you}"
            "\n\nDevolva apenas os oito parágrafos, um por linha, sem numeração, "
            "sem títulos e sem comentários."
        ),
    },
}


def script_guide(language: str | None = None) -> dict:
    """How to write a good reference script, for people cloning their own voice."""
    lang = language if language in GUIDE else "en"
    return {"language": lang, **GUIDE[lang]}


def list_scripts(language: str | None = None) -> list[dict]:
    out = []
    for key, entry in SCRIPTS.items():
        langs = [language] if language else [l for l in entry if l != "label"]
        for lang in langs:
            if lang not in entry or lang == "label":
                continue
            s = entry[lang]
            out.append({
                "situation": key,
                "label": entry["label"],
                "language": lang,
                "title": s["title"],
                "direction": s["direction"],
                "lines": s["lines"] + [CONSENT[lang]],
            })
    return out
