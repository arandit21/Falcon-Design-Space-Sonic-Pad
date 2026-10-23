from pathlib import Path
import tempfile,json,shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/windows"))
import install

testbase=Path(__file__).resolve().parent/'test_runs'
testbase.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='falcon_install_',dir=str(testbase)) as folder:
    assert Path(folder).resolve().is_relative_to(testbase.resolve())
    root=Path(folder);app=root/'app';conf=root/'conf';keys=root/'old_keys';app.mkdir();conf.mkdir();keys.mkdir()
    (keys/'falcon_sonic_rsa').write_text('fixture private key; not a real key')
    (keys/'falcon_sonic_rsa.pub').write_text('fixture public key')
    original={'Basic':{'Language':1,'Unit':0},'KeepUserSetting':{'value':42}}
    install.write_json(conf/'falcondesignspace.conf',original)
    original_camera={'version':'1.7.9','CameraConfig':[{'OTHER_MACHINE':[{'Other camera':[{'custom':True}]}]}]}
    install.write_json(conf/'camera'/'cameraConfig.txt',original_camera)
    profile={'version':'1.7.9','CameraConfig':[{'A1_TEST_DEVICE':[{'Creality Falcon Camera (Sonic Pad)':[{'Standard Plate':[{'IsCalibration':True,'marker':123}]}]}]}]}
    install.write_json(app/'calibration.json',profile)
    install.install(app,conf,keys/'falcon_sonic_rsa',make_shortcuts=False)
    assert install.read_json(conf/'falcondesignspace.conf',{})==dict(original,Basic={'Language':9,'Unit':0})
    after=install.read_json(conf/'camera'/'cameraConfig.txt',{})
    assert after['CameraConfig'][0]==original_camera['CameraConfig'][0]
    assert len(after['CameraConfig'])==2
    # An update preserves the user's newer camera adjustment and first backup.
    after['CameraConfig'][1]['A1_TEST_DEVICE'][0]['Creality Falcon Camera (Sonic Pad)'][0]['Standard Plate'][0]['marker']=456
    install.write_json(conf/'camera'/'cameraConfig.txt',after)
    install.install(app,conf,keys/'falcon_sonic_rsa',make_shortcuts=False)
    assert install.read_json(conf/'camera'/'cameraConfig.txt',{})==after
    install.rollback(app,make_shortcuts=False)
    assert install.read_json(conf/'falcondesignspace.conf',{})==original
    assert install.read_json(conf/'camera'/'cameraConfig.txt',{})==original_camera
    assert (keys/'falcon_sonic_rsa').read_text()==(app/'.ssh'/'falcon_sonic_rsa').read_text()
    # A custom/protected program directory can keep mutable state per user.
    custom=root/'Program Folder';custom.mkdir();state=root/'User Data';shutil.copy2(app/'calibration.json',custom/'calibration.json')
    install.install(custom,conf,keys/'falcon_sonic_rsa',make_shortcuts=False,data_root=state)
    assert (custom/'user_data_path.txt').read_text()==str(state.resolve())
    assert (state/'.ssh'/'falcon_sonic_rsa').read_text()==(keys/'falcon_sonic_rsa').read_text()
    assert (state/'connection.ini').is_file()
    assert not (custom/'.ssh').exists()
print('PASS: install, Russian UI, calibration merge, update preservation and rollback; real user settings untouched')
