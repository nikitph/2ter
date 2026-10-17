# EPISODE 01 — THE TEMPLE (concept video)

A 60-second concept film rendered entirely from code: no stock footage and no AI
video model. Every shot is drawn procedurally, then passed through a simulated
1987 PAL camcorder (auto-gain noise, chroma bleed, edge-enhancement halos,
tracking jitter, head-switching noise, a burned-in date stamp). Sanskrit
dialogue is shown as burned-in subtitles with English translations underneath.

| Time | Shot | How it's made |
|---|---|---|
| 00:00–00:12 | Expedition briefing | Office drawn in 2D: officer backlit by the window, ceiling fan, steel cupboard, Survey of India sheet in perspective. The photo is placed on the desk and the officer's finger traces the route. |
| 00:12–00:25 | The hills | Layered fractal ridges in an overexposed sky. The jeep is parked and the team walks on foot. Wind gusts drive both the camera shake and the mic buffeting. The guide stops and points. The camera searches the slope and the autofocus hunts until the carved lintel resolves. |
| 00:25–00:39 | The temple | Room drawn in perspective with eroded reliefs, broken pillars and rubble, lit only by an incandescent torch beam. One researcher brushes the jamb of the buried door. |
| 00:39–00:51 | Opening | Close-up. Rubble is lifted by hand and a crowbar goes into the seam. The door grinds inward in stick-slip jerks, and dust breathes out into the beam. |
| 00:51–01:00 | Inner chamber | A ray-cast corbelled dome, 34 m in radius, with a visible volumetric torch beam. The scuff echoes back about 2.6 s later, then the film cuts to black. |

The sound is synthesized too: fan and fluorescent hum, gravel footsteps,
wind buffeting, a distant kite, brushing, stone scrapes, the door thud and an
air rush. Each location has its own reverb, and everything goes through a
camcorder mic chain with AGC pumping, soft clipping, band-limiting and tape
hiss. When the film cuts to black, the sound cuts to dead silence too.

## Run

```bash
pip install -r requirements.txt          # also needs ffmpeg on PATH
python render.py                         # -> out/the_temple_ep01.mp4 (about 15 min on 4 cores)
python render.py --stills 3 20 31 45 55  # quick preview frames -> out/still_*.png
```

## Adding voices

The film has no voices yet; the subtitles carry the dialogue. To add voices,
record the lines (or generate them) and save them as WAV files:

```
vo/officer_1.wav     स्थानीयेन आदिवासिना प्राचीनस्य देवालयस्य स्थानं निवेदितम्।   (starts 00:01.0)
vo/officer_2.wav     स्थलस्य सर्वेक्षणं चित्राङ्कनं च कुर्वन्तु।                    (00:06.6)
vo/guide_1.wav       अत्र।                                                       (00:19.4)
vo/researcher_1.wav  अन्तः किमपि स्थानमस्ति।                                     (00:33.4)
vo/leader_1.wav      शनैः।                                                       (00:44.0)
```

Then re-run `python render.py`. Each line is mixed in at its subtitle time,
through the same room acoustics and camcorder mic as the rest of the sound.

## Tweaking

- Timing: scene boundaries and subtitles are in `common.py` (`SCENES`, `SUBTITLES`).
- Shots: one class per shot in `scenes.py`. Camera moves, the torch path and
  focus are keyframed with `kf(t, [(time, value), ...])` in each `frame()`.
- The tape look is in `camcorder()` in `render.py`.
- The sound is in `audio.py`.

Fonts are under the SIL Open Font License: Noto Sans Devanagari, Roboto
Condensed and VT323.
