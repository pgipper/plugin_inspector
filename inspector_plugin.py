# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name			 	 : QGIS Plugin Inspector
Description          : Get various info about active plugins
Date                 : 2019-08-26
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from PyQt5.QtGui import QIcon
from .widgets import InspectorFactory
from .settings import PLUGIN_DISPLAY_NAME


class InspectorPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.factory = None

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "inspector.png"))
        self.factory = InspectorFactory(PLUGIN_DISPLAY_NAME, icon)
        self.iface.registerDevToolWidgetFactory(self.factory)

    def unload(self):
        self.iface.unregisterDevToolWidgetFactory(self.factory)
