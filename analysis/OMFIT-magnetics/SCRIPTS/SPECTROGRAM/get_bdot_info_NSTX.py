# variables
device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
workdir = root['SETTINGS']['REMOTE_SETUP']['workDir']
server = root['SETTINGS']['REMOTE_SETUP']['server']

if is_device(device, ['NSTX']):
    # have to do this on PPPL!
    root['SETTINGS']['REMOTE_SETUP']['serverPicker'] = 'pppl_flux'

    # check variables
    if shot is None:
        printe("Enter a valid shot number to get spectrogram bdot info")
        OMFITx.End(what='all')

    # ------ read hf and hn info from config files -------
    # ---- not ideal, but the only way at the moment -----

    basedir = '/u/eric/nstx/mm/'
    general = {'hn': {'filename_config': basedir + 'config_hn.mm'}, 'hf': {'filename_config': basedir + 'config_hf.mm'}}
    data = {}
    for what in ['hn', 'hf']:
        data[what] = OMFITtree()
        fina = general[what]['filename_config']

        script1 = (
            '''#!/usr/bin/env python3
import sys
filename=sys.argv[1]
with open(filename, "r") as f:
   lines = [line.rstrip("\\n").replace("\\t", " ").split() for line in f]
print(lines)
        ''',
            'get_info.py',
        )

        executable1 = f'''
        module purge
        module load python
        chmod +x ./get_info.py
        ./get_info.py {fina}
        '''

        std_out = []
        std_err = []

        OMFITx.executable(root, clean=False, server=server, executable=executable1, std_out=std_out, std_err=std_err, script=script1)

        lines = eval(std_out[-2])

        shots = [a[0] for a in lines[1:-1]]
        filenm = [a[1] for a in lines[1:-1]]
        general[what]['shots'] = shots
        general[what]['fn'] = filenm

        for ind, sh in enumerate(np.sort(shots)):
            if shot >= int(sh):
                ifi = ind
        tree = ''
        filename = basedir + filenm[ifi]
        data[what]['filename'] = filename

        script2 = (
            '''#!/usr/bin/env python3
import sys
filename=sys.argv[1]
with open(filename, "r") as f:
    lines = [line.strip('\\n') for line in f]
print(lines)
        ''',
            'get_info2.py',
        )

        executable2 = f'''
        module purge
        module load python
        chmod +x ./get_info2.py
        ./get_info2.py {filename}
        '''

        std_out = []
        std_err = []

        OMFITx.executable(root, clean=False, server=server, executable=executable2, std_out=std_out, std_err=std_err, script=script2)

        lines = eval(std_out[-2])

        print('read file ' + filenm[ifi] + ' for shot ' + str(shot))

        if what == 'hf':
            ntor, nfp, npol = lines[0].split()
        else:
            ntor = lines[0]
            nfp = '0'
            npol = '0'
        na = lines[1]
        tree = lines[2]

        print(ntor, nfp, npol)

        nch = int(ntor) + int(nfp) + int(npol)
        chn = []
        cnam = []
        sig = []
        tor = []
        pol = []
        tdl = []
        point = []
        for i in range(nch):
            index = i + 3
            if what == 'hf':
                if shot < 200000:
                    to, po, sign, chan, point = lines[index].split()
                    td = 0.0
                else:
                    to, po, sign, td, chan, point = lines[index].split()
            else:
                to, sign, chan, point = lines[index].split()
                po = -33.47
                td = 0

            chn.append(chan)
            cnam.append(point)
            sig.append(sign)
            tor.append(float(to))
            pol.append(float(po))
            tdl.append(td)

        oe1, oe2 = lines[-1].split()

        data[what]['MDShost'] = 'skylark.pppl.gov:8501'
        data[what]['tree'] = tree
        data[what]['na'] = float(na) * np.ones(nch)
        data[what]['nch'] = nch

        data[what]['chn'] = chn
        data[what]['sig'] = sig
        data[what]['cnam'] = cnam
        data[what]['tor'] = tor
        data[what]['pol'] = pol
        data[what]['tdl'] = tdl

        data[what]['ntor'] = ntor
        data[what]['nfp'] = nfp
        data[what]['npol'] = npol
        data[what]['oe1'] = oe1
        data[what]['oe2'] = oe2
elif device == 'DIII-D':
    printe(f"{device} is not supported yet...but coming soon")
    OMFITx.End()
else:
    printe(f"Spectrograms do not support {device} yet.")
    OMFITx.End()


if device not in list(root['DATA']):
    root['DATA'][device] = OMFITtree()

root['DATA'][device].update(general)


if 'SPECTROGRAM' not in list(root['INPUTS']):
    root['INPUTS']['SPECTROGRAM'] = OMFITtree()

if device not in list(root['INPUTS']['SPECTROGRAM']):
    root['INPUTS']['SPECTROGRAM'][device] = OMFITtree()

if shot not in list(root['INPUTS']['SPECTROGRAM']['NSTX']):
    root['INPUTS']['SPECTROGRAM'][device][shot] = OMFITtree()

root['INPUTS']['SPECTROGRAM'][device][shot].update(data)
