"""Blender (Cycles) product showcase of the smlibpy phone stand.

blender -b -P showcase.py -- models render [--still FRAME] [--samples N] [--res WxH]

Reads stand.glb and phone.glb from the first directory (written by phone_stand.py) and writes
PNG frames, or one still, plus showcase.blend into the second.
"""
import math
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
opt = dict(zip(argv[2::2], argv[3::2]))
STILL = int(opt["--still"]) if "--still" in opt else None
SAMPLES = int(opt.get("--samples", 64))
RES = tuple(int(v) for v in opt.get("--res", "1920x1080").split("x"))
FPS, SECONDS = 24, 6
FRAMES = FPS * SECONDS

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def srgb(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1.0]


def principled(name, color, rough, metal=0.0, coat=0.0, coat_rough=0.03, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    if emission:
        b.inputs["Emission Color"].default_value = srgb(emission)
        b.inputs["Emission Strength"].default_value = strength
    return m


# ---------------------------------------------------------------- the parts
def import_glb(path, name, mat):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for o in new:
        if o.name in bpy.data.objects and o is not obj:
            bpy.data.objects.remove(o)
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


stand_mat = principled("stand", "#2f7d47", rough=0.38, coat=0.25, coat_rough=0.25)
body_mat = principled("phone body", "#2b2d31", rough=0.28, metal=1.0)
screen_mat = principled("phone screen", "#050608", rough=0.04, coat=1.0, coat_rough=0.0,
                        emission="#1b3a6b", strength=1.4)
# wallpaper: a vertical gradient across the phone, from deep blue to violet
nt = screen_mat.node_tree
tc, sep, ramp = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeValToRGB")
nt.links.new(tc.outputs["Generated"], sep.inputs[0])
nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
ramp.color_ramp.elements[0].color = srgb("#0b1d4a")
ramp.color_ramp.elements[1].color = srgb("#5b2a86")
nt.links.new(ramp.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Emission Color"])

stand = import_glb(f"{SRC}/stand.glb", "Stand", stand_mat)
phone = import_glb(f"{SRC}/phone.glb", "Phone", body_mat)

# the screen: faces whose normal is the phone's front direction (leaning 20 deg back)
phone.data.materials.append(screen_mat)
front = Vector((math.cos(math.radians(20)), 0, math.sin(math.radians(20))))
for p in phone.data.polygons:
    if p.normal.dot(front) > 0.995:
        p.material_index = 1

lo = Vector([min(v[i] for o in (stand, phone) for v in (o.matrix_world @ Vector(c) for c in o.bound_box))
             for i in range(3)])
hi = Vector([max(v[i] for o in (stand, phone) for v in (o.matrix_world @ Vector(c) for c in o.bound_box))
             for i in range(3)])
print("scene bbox (m):", tuple(round(x, 4) for x in lo), tuple(round(x, 4) for x in hi))

# turntable pivot under the middle of the stand
pivot = bpy.data.objects.new("Turntable", None)
scene.collection.objects.link(pivot)
pivot.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0)
for o in (stand, phone):
    o.parent = pivot
    o.matrix_parent_inverse = pivot.matrix_world.inverted()
pivot.rotation_euler = (0, 0, math.radians(-35))
pivot.keyframe_insert("rotation_euler", index=2, frame=1)
pivot.rotation_euler = (0, 0, math.radians(-35 + 360))
pivot.keyframe_insert("rotation_euler", index=2, frame=FRAMES + 1)   # loops seamlessly

# ---------------------------------------------------------------- studio
def cyclorama(width=3.0, depth=2.0, height=1.5, radius=0.5, seg=24):
    bm = bmesh.new()
    prof = [(-depth / 2, 0.0)]
    for i in range(seg + 1):
        a = -math.pi / 2 + (math.pi / 2) * i / seg
        prof.append((depth / 2 - radius + radius * math.cos(a), radius + radius * math.sin(a)))
    prof.append((depth / 2, height))
    rows = [[bm.verts.new((x, y, z)) for y, z in prof] for x in (-width / 2, width / 2)]
    for j in range(len(prof) - 1):
        bm.faces.new((rows[0][j], rows[1][j], rows[1][j + 1], rows[0][j + 1]))
    me = bpy.data.meshes.new("Cyclorama")
    bm.to_mesh(me)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("Cyclorama", me)
    scene.collection.objects.link(ob)
    return ob


cyc = cyclorama()
cyc.location = (pivot.location.x, pivot.location.y - 0.35, -0.0001)
cyc.data.materials.append(principled("backdrop", "#a9a49c", rough=0.55))


def area(name, loc, size, energy, color="#ffffff", target=(0, 0, 0.06)):
    d = bpy.data.lights.new(name, "AREA")
    d.shape, d.size, d.energy, d.color = "DISK", size, energy, srgb(color)[:3]
    ob = bpy.data.objects.new(name, d)
    scene.collection.objects.link(ob)
    ob.location = loc
    tgt = Vector(target) + Vector((pivot.location.x, pivot.location.y, 0))
    ob.rotation_euler = (tgt - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


cx, cy = pivot.location.x, pivot.location.y
area("Key", (cx + 0.45, cy - 0.55, 0.55), 0.6, 26, "#fff4e8")
area("Fill", (cx - 0.6, cy - 0.35, 0.25), 0.8, 7, "#e8f0ff")
area("Rim", (cx - 0.15, cy + 0.55, 0.45), 0.3, 40, "#ffffff")

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = srgb("#2a2c30")
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25

# ---------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 70
cam_data.dof.use_dof = True
cam_data.dof.aperture_fstop = 5.6
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
focus = bpy.data.objects.new("Focus", None)
scene.collection.objects.link(focus)
focus.location = (cx, cy, 0.065)
cam_data.dof.focus_object = focus
track = cam.constraints.new("TRACK_TO")
track.target, track.track_axis, track.up_axis = focus, "TRACK_NEGATIVE_Z", "UP_Y"

elev = math.radians(17)
for frame, dist in ((1, 0.78), (FRAMES, 0.62)):             # slow push-in
    cam.location = (cx, cy - dist * math.cos(elev), 0.065 + dist * math.sin(elev))
    cam.keyframe_insert("location", frame=frame)
for fc in cam.animation_data.action.fcurves if hasattr(cam.animation_data.action, "fcurves") else []:
    for k in fc.keyframe_points:
        k.interpolation = "SINE"
try:
    for fc in pivot.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
except AttributeError:   # layered actions (Blender 5): walk the channelbags
    for act, ip in ((pivot.animation_data.action, "LINEAR"), (cam.animation_data.action, "SINE")):
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for k in fc.keyframe_points:
                            k.interpolation = ip

# ---------------------------------------------------------------- render
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_adaptive_sampling = True
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.cycles.max_bounces = 4
scene.cycles.adaptive_threshold = 0.03
scene.render.use_persistent_data = True
scene.render.resolution_x, scene.render.resolution_y = RES
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.7
scene.render.image_settings.file_format = "PNG"

if STILL is not None:
    scene.frame_set(STILL)
    scene.render.filepath = f"{OUT}/still_{STILL:04d}.png"
    bpy.ops.render.render(write_still=True)
else:
    bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/showcase.blend")
    scene.render.filepath = f"{OUT}/frames/f_"
    bpy.ops.render.render(animation=True)
