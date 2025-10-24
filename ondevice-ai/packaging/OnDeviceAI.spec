# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

project_root = os.path.abspath(os.getcwd())
assets_dir = os.path.join(project_root, 'assets')
plugins_dir = os.path.join(project_root, 'plugins')
models_dir = os.path.join(project_root, 'ml_models')

datas = []
if os.path.isdir(plugins_dir):
    datas.append((plugins_dir, 'plugins'))
if os.path.isdir(models_dir):
    datas.append((models_dir, 'ml_models'))

icon_path = None
icns = os.path.join(assets_dir, 'icon.icns')
if os.path.isfile(icns):
    icon_path = icns

a = Analysis(
    [os.path.join(project_root, 'automation_daemon.py')],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=['flask','yaml','httpx','numpy','msgpack','assistant_pb2','assistant_pb2_grpc'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OnDeviceAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed app
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OnDeviceAI'
)

app = BUNDLE(
    coll,
    name='OnDeviceAI.app',
    icon=icon_path,
    bundle_identifier='ai.ondevice.app',
)
