"""A phone stand modelled with smlibpy, plus a phone to show it in use.

    pip install smlibpy
    python phone_stand.py            # writes models/ and media/ next to this file
"""

from pathlib import Path

from smlibpy import *

HERE = Path(__file__).parent


def stand() -> Part:
    # side profile in XZ: base plate and a 6 mm back leaning 20 deg rearward
    side = Polygon((25.8, 0), (90, 0), (90, 6), (30, 6), (3.32, 79.3), (-2.32, 77.2))
    s = side.on(Plane.front).extrude(70)                   # 70 mm wide, toward -Y
    s += Box(4, 70, 18).translate(44, -35, 9)              # front lip holds the phone
    s = s.fillet(s.edges().parallel_to(Y), 1.5)
    s -= Box(16, 22, 30).translate(41, -35, 0)             # cable slot through lip and base
    return s.named("stand").colored("#5aa36b")


def phone() -> Part:
    # 8 x 72 x 150 slab, rounded, resting on the base against the back
    p = Box(8, 72, 150).translate(4, 0, 75)
    p = p.fillet(p.edges().parallel_to(X), 9)
    p = p.fillet(p.edges(), 2.5)
    return p.rotate(Y, -20).translate(30.47, -35, 5.36).named("phone")


if __name__ == "__main__":
    s, p = stand(), phone()
    clash = s & p
    assert not clash or clash.volume < 1e-6, "phone intersects the stand"
    print(f"stand: valid={s.is_valid()}  volume={s.volume:.1f} mm3  "
          f"mass={s.mass_properties(density=1.24e-3).mass:.1f} g (PLA)")

    (HERE / "models").mkdir(exist_ok=True)
    (HERE / "media").mkdir(exist_ok=True)
    s.export(HERE / "models/stand.step")
    s.export(HERE / "models/stand.stl", tolerance=0.01)
    # meshes for Blender (glTF, which Blender imports natively)
    s.export(HERE / "models/stand.glb", tolerance=0.01, angle=4, edges=False)
    p.export(HERE / "models/phone.glb", tolerance=0.01, angle=4, edges=False)
    render(s, path=HERE / "media/stand_iso.png", size=(700, 520))
    render(s, path=HERE / "media/stand_drawing.png", drawing="first-angle", size=(1100, 780))
