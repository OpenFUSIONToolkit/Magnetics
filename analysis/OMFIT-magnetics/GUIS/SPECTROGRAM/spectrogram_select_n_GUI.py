'''
GUI to personalize the colors of the spectrogram
'''
name = root['SETTINGS']['SPECTROGRAM']['name']
phi1 = root['SETTINGS']['SPECTROGRAM']['p1']['phi']
phi2 = root['SETTINGS']['SPECTROGRAM']['p2']['phi']

root['SETTINGS']['SPECTROGRAM']['what_to_plot'] = 'selected'

OMFITx.TitleGUI(name)

dtheta = phi1 - phi2


def calculate_nrange(dtheta):

    nmodes = np.ceil(180.0 / abs(dtheta) - 0.5) * 2
    mlo = int(-0.5 * nmodes)
    mhi = int(0.5 * nmodes)
    nrange = np.arange(mlo, mhi + 1)

    return nrange


nrange = calculate_nrange(dtheta)

color_options = [
    # list( plt.rcParams['axes.prop_cycle'].by_key()['color']) +  # the GUI (tkinter in general I think) does not like the abbreviated version of the colors
    'black',
    'blue',
    'green',
    'red',
    'cyan',
    'magenta',
    'yellow',
    'aliceblue',
    'azure',
    'beige',
    'blueviolet',
    'brown',
    'coral',
    'cornflowerblue',
    'cornsilk',
    'crimson',
    'firebrick',
    'forestgreen',
    'fuchsia',
    'gold',
    'goldenrod',
    'gray',
    'greenyellow',
    'grey',
    'hotpink',
    'indianred',
    'indigo',
    'ivory',
    'khaki',
    'lavender',
    'lime',
    'midnightblue',
    'mintcream',
    'mistyrose',
    'moccasin',
    'navy',
    'olive',
    'orange',
    'orangered',
    'orchid',
    'papayawhip',
    'peachpuff',
    'peru',
    'pink',
    'plum',
    'powderblue',
    'purple',
    'royalblue',
    'salmon',
    'skyblue',
    'tomato',
    'turquoise',
    'violet',
]


def init():
    root['__scratch__']['selected'] = {}
    for ind, nn in enumerate(nrange):

        if nn in root['SETTINGS']['SPECTROGRAM']['plotting_parameters']['nrange']:
            (ind,) = np.where(nn == root['SETTINGS']['SPECTROGRAM']['plotting_parameters']['nrange'])
            print(ind[0])
            print(root['SETTINGS']['SPECTROGRAM']['plotting_parameters']['ncolor'][ind[0]])
            root['__scratch__']['selected'][nn] = {
                'status': True,
                'color': root['SETTINGS']['SPECTROGRAM']['plotting_parameters']['ncolor'][ind[0]],
            }
        else:
            root['__scratch__']['selected'][nn] = {'status': False, 'color': 'white'}


if 'selected' not in list(root['__scratch__']):
    init()
if max(nrange) != max(list(root['__scratch__']['selected'])):
    init()


for nn in np.sort(nrange):
    if root['__scratch__']['selected'][nn]['status']:
        color = root['__scratch__']['selected'][nn]['color']
    else:
        color = 'white'

    OMFITx.CheckBox("root['__scratch__']['selected'][" + str(nn) + "]['status']", lbl=str(nn), default=False, bg=color, updateGUI=True)

    OMFITx.ComboBox("root['__scratch__']['selected'][" + str(nn) + "]['color']", color_options, lbl='', default='white', updateGUI=True)


def plot_and_quit():
    nrange = []
    ncolor = []
    for nn in list(root['__scratch__']['selected']):
        if root['__scratch__']['selected'][nn]['status']:
            nrange.append(nn)
            ncolor.append(root['__scratch__']['selected'][nn]['color'])
    root['SETTINGS']['SPECTROGRAM']['plotting_parameters'] = {'nrange': nrange, 'ncolor': ncolor}
    root['PLOTS']['SPECTROGRAM']['plot_spectrogram'].run()
    OMFITx.CloseGUI()


OMFITx.Button('Plot and Close', lambda: plot_and_quit())
