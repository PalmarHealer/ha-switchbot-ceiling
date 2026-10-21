# SwitchBot RGBICWW Ceiling Light for Home Assistant

Local Bluetooth control of the SwitchBot RGBICWW Ceiling Light (W1162000), with the
white light and the RGBIC color ring as two separate lights.

Matter on this lamp merges both parts into one light, so it jumps to RGB on dimming,
always fades out slowly and has no segment effects. This integration talks the lamp's
own BLE protocol instead.

## Entities

| Entity | What it does |
|---|---|
| Light **White** | on/off, brightness, 2700–6500 K |
| Light **Color** | on/off, RGB, brightness, effects (8 segment effects + 25 scenes) |
| Text **Effect colors** | 1–10 hex colors used by the segment effects, e.g. `FF0000,00FF00,0000FF` |
| Number **Effect speed** | speed of the running segment effect |
| Select **Switch-on fade** / **Switch-off fade** | device default, instant, or 5 s … 1 h |

`transition:` on `light.turn_on` / `light.turn_off` overrides the fade per call.

## Actions

- `switchbot_ceiling.set_segment_effect`: `effect` (flow, rebound, breath, cover, pile,
  wave, flash, comet), `colors` (list of `[r, g, b]`, max 10), optional `speed`
- `switchbot_ceiling.send_command`: raw hex command, for protocol experiments; the reply
  is fired as event `switchbot_ceiling_response`

## Setup

1. HACS → Custom repositories → add this repository (type *Integration*), install, restart.
2. The lamp must be added to a SwitchBot account once (SwitchBot app), because its BLE
   commands are encrypted with a key that only exists in that account.
3. Settings → Devices & services → Add integration → *SwitchBot RGBICWW Ceiling Light*,
   then sign in with the SwitchBot account (used once to fetch the key, not stored) or
   enter key id and key manually.

The lamp has to be in Bluetooth range of Home Assistant or an ESPHome Bluetooth proxy.
