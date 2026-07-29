# Voice reference recording: setup and script

The script now lives inside the studio, on the same screen where you record:
**http://localhost:3000/voices**, then **New voice**, then pick
**"Master reference (90s, recommended)"**. This file is a copy for reading away
from the machine.

About 90 seconds. 219 words including the consent line.

## Before you press record

- Best mic, not the phone. A hand's width away, angled slightly off your mouth
  so plosives miss the capsule.
- Kill the room: no fan, no laptop noise, window shut.
- Do not turn on noise suppression on your microphone, and do not run the file
  through a cleanup app before uploading. Record somewhere quiet instead. The
  studio measures the take and offers its own cleanup afterwards, and it shows
  you what that cleanup costs.
- One continuous take. If you fumble a line, pause and say it again, we can
  trim later.

## How to read it

Read at the pace and warmth you want the clone to speak, because it copies your
delivery, not just your timbre. This voice will narrate the trailer, the demo
and the tutorials, so read it the way you want those to sound.

Breathe between paragraphs. Do not perform, just talk.

---

I am recording this so the system can learn my voice, and I am reading it the
way I want that voice to sound: unhurried, warm, and clear.

Most good work starts the same way: a quiet room, a blank page, and a question
worth answering.

Some days that means choosing a typeface. Some days it means teaching a machine
to do something useful. Both jobs reward patience.

Let me count, because numbers come up often: one, two, three, four, five, six,
seven, eight, nine, ten. Thirty, sixty, ninety. Two thousand and twenty six.

Would it be useful if the whole thing ran on your own machine, with nothing ever
leaving the building? That question is worth sitting with.

There is real pleasure in shipping something finished. I am a poor judge of my
own work until it is out in the world, and then the usual thing happens: I
change one detail, then another, then I make myself stop.

Good work is just choices, made slowly and defended later. The rest is patience,
and a room quiet enough to hear yourself think.

If it sounds like me here, it will sound like me everywhere else. So this is the
take that matters.

This recording is my voice, and I consent to using it for my own voice profile.

---

## Why this script

It is built to cover the full range of English sounds while still sounding like
something you would actually say, because a natural read clones better than a
phonetic drill. The ordinary looking parts are doing work:

- "pleasure", "usual", "judge", "change" and "choosing" cover the soft
  consonants that phoneme lists usually miss.
- "worth", "both", "think" against "that", "the", "then" cover both kinds of
  "th".
- The number run gives clean digits for tutorial narration.
- The question gives the model a rising intonation to copy, so the clone can ask
  something without sounding flat. The mic answer on the website opens by
  reacting to the visitor, so it needs this.
- The last line changes register slightly, which gives the clone some range
  instead of one flat colour.

The studio appends the consent line automatically. Read it, it is the record
that this voice is yours.

## What a clone inherits, measured

These numbers come from real takes on this machine, not from theory. They are
the most useful thing to know before you record.

**A clone inherits the room, not just the voice.** A reference with 43 dB
between voice and room produced a clone whose background sat at -53 dB. A
reference with 55 dB produced one at -68 dB. Nothing downstream fixes this.

**Cleaning the output barely helps: about 2 dB.** By the time the noise is in
the generated audio it is part of the voice's character, not a layer sitting on
top of it that a filter can lift off.

**Cleaning the reference helps more: about 5 dB.** Running
`highpass=f=70,afftdn=nr=14:nf=-48:tn=1` over a reference moved its noise floor
from -60.4 to -65.4 dB and its voice-above-room from 47.4 to 52.0, while leaving
the 15.8 kHz reach untouched. The studio offers exactly this under "Clean up".

**But cleaning the reference changes the delivery.** A denoised reference read
15 to 37 percent faster than the same recording untouched. That is why the
studio never cleans anything silently: it builds a second voice and leaves the
original alone, so you can hear both and keep the one that sounds like you.

**Only about ten seconds reach the engine's ear.** The engine conditions its
decoder on the first ten seconds of the reference file and its accent-carrying
token prompt on the first six; the rest feeds one weak averaged embedding. The
studio therefore scans the whole take for its strongest ten seconds (the most
voiced, most pitch-alive stretch, snapped to a speech onset) and leads with
that window automatically, instead of whatever happened to be the stiff first
line of the read. The full recording still earns its length: it is the pool
the window is found in, it stays for playback and quality checks, and it
becomes training data the day the voice is fine-tuned. A longer recording in
one consistent sitting raises the odds of a great window.

**Bandwidth is decided by the microphone and cannot be recovered.** A Bluetooth
headset in call mode, or a virtual "voice chat" microphone, caps the voice
around 2 to 8 kHz. The engines generate at 24 kHz, so everything above the cap
is invented by the model, and what it invents is generic. That shows up as
background noise or a drifting accent. A phone's own voice recorder app,
recorded close in a quiet room, beats most desk setups.

**Do not send the file through a messaging app.** WhatsApp and similar re-encode
to narrowband and apply automatic gain. One test file came back with 2053
samples clipped flat against full scale. Transfer by cable, drive or email.

**The format does not matter.** Whatever your phone or recorder wrote, hand it
over: m4a, wma, amr, aiff, an mp4 with an audio track. The studio converts it
on the way in. What matters is the microphone and the room, not the container.

## Note for the public repo

The script itself is generic on purpose, so it ships fine in
`server/app/scripts_data.py`, alongside a Portuguese version, two more registers
and a written guide with an LLM prompt for building your own. This file is just
a convenience copy and can be excluded.
