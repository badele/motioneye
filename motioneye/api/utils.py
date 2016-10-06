import os
import importlib

def get_modules_api():
    modules = dict()

    # Search API submodule
    rootfolder = os.path.dirname(__file__)
    folders = [d for d in os.listdir(rootfolder) if os.path.isdir(os.path.join(rootfolder, d))]
    for folder in folders:
        # Import module
        modulename = 'motioneye.api.%(folder)s' % {'folder': folder}
        classname = '%(folder)sHandler' % {'folder': folder.title()}
        module = importlib.import_module(modulename)

        # Get class
        modules[modulename] = dict()
        modules[modulename]['description'] = getattr(module, 'DESCRIPTION')
        modules[modulename]['routes'] = getattr(module, 'ROUTES')
        modules[modulename]['class'] = getattr(module, classname)

    return modules