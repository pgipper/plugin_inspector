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



def classFactory(iface):
    from .inspector_plugin import InspectorPlugin
    return InspectorPlugin(iface)
