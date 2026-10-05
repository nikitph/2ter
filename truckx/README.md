# TruckX Fleet Command (concept)

Fleet management that plays like a strategy game. You watch an isometric, low-poly world where
12 trucks run real lanes between a port, a yard, a DC, a customer and a fuel stop, and every
TruckX product shows up as part of the game:

- **AI dashcams**: harsh braking, phone use, tailgating, drowsiness, rolling stops and speeding
  show up as pulses in the world and as cards in the alert feed. Click **View clip** to fly to the
  truck and open a *live* road-facing, driver-facing, chase or drone camera, rendered from the
  truck's own point of view.
- **ELD / HOS**: each truck's tag shows remaining drive time. The truck card has Drive, Shift,
  Cycle and Break rings plus a duty-status bar. Drivers relay at the yard when their hours run low.
- **GPS and geofences**: dashed geofences light up when trucks dwell at docks. Loads carry a BOL,
  cargo, weight, trailer, ETA and a progress bar.
- **Engine diagnostics and DVIR**: J1939 fault codes, idling and inspection defects.
- **Freight flow**: At yard → Loading → In transit → Unloading → Delivered, plus on-time %.

All data is simulated. No backend is needed.

## Run

ES modules need an HTTP server, so `file://` won't work:

```bash
cd truckx
python3 -m http.server 8000
# open http://localhost:8000
```

Three.js is vendored in `vendor/`, so it runs offline.

## Controls

| Action | Input |
| --- | --- |
| Select truck | Click a truck or its tag |
| Pan / rotate / zoom | Left-drag / right-drag / scroll |
| Pause, 1×, 4×, 12× | `Space`, `1`, `2`, `3` |
| Back to overview | `Esc` |
