from calibre.customize import InterfaceActionBase


class TxtNovaToolkitBase(InterfaceActionBase):
    name = 'TXT Nova Toolkit'
    description = 'Import, update and export TXT novels using standard filenames'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'OpenCode'
    version = (1, 2, 1)
    minimum_calibre_version = (5, 0, 0)

    actual_plugin = 'calibre_plugins.txt_nova_toolkit.ui:TxtNovaToolkitAction'
