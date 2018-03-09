# -*- coding: utf-8 -*-
#
# (c) 2016 Boundless, http://boundlessgeo.com
# This code is licensed under the GPL 2.0 license.
#
from __future__ import absolute_import
from builtins import str
from builtins import object
import codecs
import os
import shutil
import zipfile
import uuid
from qgis.core import *
from qgis.utils import iface
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtSvg import *

from .utils import *
from . import utils
from .settings import *
from .olwriter import exportStyles, layerToJavascript
from collections import OrderedDict
from operator import attrgetter
from qgis.utils import plugins_metadata_parser
from qgiscommons2.files import tempFilenameInTempFolder
from qgiscommons2.settings import pluginSetting
from .webbappwidget import WebAppWidget



def writeWebApp(appdef, folder, progress):
    progress.setText("Copying resources files")
    dst = os.path.join(folder, "webapp")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    QDir().mkpath(dst)
    sdkFolder = os.path.join(os.path.dirname(__file__), "websdk_full")
    shutil.copy(os.path.join(sdkFolder, "full-debug.js"), dst)

    QDir().mkpath(os.path.join(dst, "data"))

    jsFolder = os.path.join(os.path.dirname(__file__), "js")
    jsDstFolder = os.path.join(dst, "resources","js")
    shutil.copytree(jsFolder, jsDstFolder)
    cssFolder = os.path.join(os.path.dirname(__file__), "css")
    cssDstFolder = os.path.join(dst, "resources","css")
    shutil.copytree(cssFolder, cssDstFolder)
    shutil.copy(os.path.join(sdkFolder, "ol.css"), cssDstFolder)
    layers = appdef["Layers"]
    exportLayers(layers, dst, progress,
                 appdef["Settings"]["Precision for GeoJSON export"],
                 appdef["Settings"]["App view CRS"])

    class App(object):
        tabs = []
        ol3controls = []
        tools = []
        panels = []
        mappanels = []
        variables = []
        scripts = []
        scriptsbody = []
        posttarget = []
        imports = []
        aftermap = []
        def newInstance(self):
            _app = App()
            _app.tabs = list(self.tabs)
            _app.ol3controls = list(self.ol3controls)
            _app.tools = list(self.tools)
            _app.panels = list(self.panels)
            _app.aftermap = list(self.aftermap)
            _app.mappanels = list(self.mappanels)
            _app.variables = list(self.variables)
            _app.scripts = list(self.scripts)
            _app.scriptsbody = list(self.scriptsbody)
            _app.posttarget = list(self.posttarget)
            _app.imports = list(self.imports)
            return _app

    _app = App()
    exportStyles(layers, dst, appdef["Settings"], "timeline" in appdef["Widgets"], _app, progress)
    writeLayersAndGroups(appdef, dst, _app, progress)

    widgets = sorted(list(appdef["Widgets"].values()), key=attrgetter('order'))
    for w in widgets:
        w.write(appdef, dst, _app, progress)

    writeCss(appdef, dst, widgets)

    baseTarget = "_self" if appdef["Settings"]["Open hyperlinks in"] == 0 else "_blank"
    _app.scripts.append("<base target='%s'>" % baseTarget)

    app = _app.newInstance()
    writeJs(appdef, dst, app, progress)
    app.scriptsbody.extend(['<script src="full-debug.js"></script>',
                            '<script src="app_prebuilt.js"></script>'])
    for layer in appdef["Layers"]:
        if layer.layer.type() == layer.layer.VectorLayer:
            app.scriptsbody.append('<script src="./data/lyr_%s.js"></script>' % safeName(layer.layer.name()))
    writeHtml(appdef, dst, app, progress, "index_debug.html")

def writeJs(appdef, folder, app, progress):
    layers = appdef["Layers"]
    viewCrs = appdef["Settings"]["App view CRS"]
    crs = QgsCoordinateReferenceSystem(viewCrs)
    mapbounds = bounds(appdef["Settings"]["Extent"] == "Canvas extent", layers, viewCrs)
    mapextent = "extent: %s," % mapbounds if appdef["Settings"]["Restrict to extent"] else ""
    maxZoom = int(appdef["Settings"]["Max zoom level"])
    minZoom = int(appdef["Settings"]["Min zoom level"])

    app.variables.append("var view = new ol.View({%s maxZoom: %d, minZoom: %d, projection: '%s'});" % (mapextent, maxZoom, minZoom, viewCrs))
    app.variables.append("var originalExtent = %s;" % mapbounds)

    canvas = iface.mapCanvas()
    canvasCrs = canvas.mapSettings().destinationCrs()
    conversionNumerator = 111325.0 if canvasCrs.mapUnits() == QgsUnitTypes.DistanceDegrees else 1
    conversionDenominator = 111325.0 if crs.mapUnits() == QgsUnitTypes.DistanceDegrees else 1
    conversion = conversionNumerator / conversionDenominator
    app.variables.append("var unitsConversion = %s;" % str(conversion))

    logoImg = appdef["Settings"]["Logo"].strip()
    logoOption = ""
    if logoImg:
        ext = os.path.splitext(logoImg)[1]
        shutil.copyfile(logoImg, os.path.join(folder, "logo" + ext))
        logoOption = ', logo: "logo%s"' % ext

    toolbarOptions = '{title:"%s"%s}' % (appdef["Settings"]["Title"], logoOption)

    variables ="\n".join(app.variables)

    app.mappanels.append('''React.createElement("div", {id: 'popup', className: 'ol-popup'},
                                    React.createElement(InfoPopup, {toggleGroup: 'navigation', map: map, hover: %s})
                                  )''' % str(appdef["Settings"]["Show popups on hover"]).lower())

    permalink = str(appdef["Settings"]["Add permalink functionality"]).lower()

    def join(array):
        if array:
            return ",\n" + ",\n".join(array)
        else:
            return ""

    values = {"@TABS@": ",\n".join(app.tabs),
                "@OL3CONTROLS@": ",\n".join(app.ol3controls),
                "@PANELS@": join(app.panels),
                "@MAPPANELS@": join(app.mappanels),
                "@TOOLBAR@": join(app.tools),
                "@TOOLBAROPTIONS@": toolbarOptions,
                "@VARIABLES@": variables,
                "@AFTERMAP@": "\n".join(app.aftermap),
                "@POSTTARGETSET@": "\n".join(app.posttarget),
                "@PERMALINK@": permalink}

    template = os.path.join(os.path.dirname(__file__), "themes",
                            appdef["Settings"]["Theme"], "app.js")
    js = replaceInTemplate(template, values)

    jsFilepath = os.path.join(folder, "app_prebuilt.js")
    with codecs.open(jsFilepath, "w", encoding="utf-8") as f:
        f.write(js)

def writeJsx(appdef, folder, app, progress):
    layers = appdef["Layers"]
    viewCrs = appdef["Settings"]["App view CRS"]
    crs = QgsCoordinateReferenceSystem(viewCrs)
    mapbounds = bounds(appdef["Settings"]["Extent"] == "Canvas extent", layers, viewCrs)
    mapextent = "extent: %s," % mapbounds if appdef["Settings"]["Restrict to extent"] else ""
    maxZoom = int(appdef["Settings"]["Max zoom level"])
    minZoom = int(appdef["Settings"]["Min zoom level"])

    app.variables.append("var view = new ol.View({%s maxZoom: %d, minZoom: %d, projection: '%s'});" % (mapextent, maxZoom, minZoom, viewCrs))
    app.variables.append("var originalExtent = %s;" % mapbounds)

    permalink = str(appdef["Settings"]["Add permalink functionality"]).lower()

    logoImg = appdef["Settings"]["Logo"].strip()
    logoOption = ""
    if logoImg:
        ext = os.path.splitext(logoImg)[1]
        shutil.copyfile(logoImg, os.path.join(folder, "logo" + ext))
        logoOption = ', logo:"logo%s"' % ext

    toolbarOptions = '{title:"%s"%s}' % (appdef["Settings"]["Title"], logoOption)

    app.mappanels.append('''React.createElement("div", {id: 'popup', className: 'ol-popup'},
                                    React.createElement(InfoPopup, {toggleGroup: 'navigation', map: map, hover: %s})
                                  )''' % str(appdef["Settings"]["Show popups on hover"]).lower())

    canvas = iface.mapCanvas()
    canvasCrs = canvas.mapSettings().destinationCrs()
    conversionNumerator = 111325.0 if canvasCrs.mapUnits() == QgsUnitTypes.Degrees else 1
    conversionDenominator = 111325.0 if crs.mapUnits() == QgsUnitTypes.Degrees else 1
    conversion = conversionNumerator / conversionDenominator
    app.variables.append("var unitsConversion = %s;" % str(conversion))

    variables ="\n".join(app.variables)

    def join(array):
        if array:
            return ",\n" + ",\n".join(array)
        else:
            return ""

    values = {"@IMPORTS@": "\n".join(app.imports),
              "@TABS@": ",\n".join(app.tabs),
                "@OL3CONTROLS@": ",\n".join(app.ol3controls),
                "@PANELS@": join(app.panels),
                "@MAPPANELS@": join(app.mappanels),
                "@TOOLBAR@": join(app.tools),
                "@TOOLBAROPTIONS@": toolbarOptions,
                "@VARIABLES@": variables,
                "@AFTERMAP@": "\n".join(app.aftermap),
                "@POSTTARGETSET@": "\n".join(app.posttarget),
                "@PERMALINK@": permalink}

    template = os.path.join(os.path.dirname(__file__), "themes",
                            appdef["Settings"]["Theme"], "app.jsx")
    jsx = replaceInTemplate(template, values)

    name = "app.jsx"
    jsxFilepath = os.path.join(folder, name)
    with codecs.open(jsxFilepath, "w", encoding="utf-8") as f:
        f.write(jsx)


def writeCss(appdef, folder, widgets):
    offset = 20
    margin = 15
    theme = appdef["Settings"]["Theme"]
    if theme == 'basic':
        offset = 84
    src = os.path.join(os.path.dirname(__file__), "themes", theme, "app.css")
    dst = os.path.join(folder, "app.css")
    with open(src) as f:
        css = f.read()
    left = offset
    right = offset
    widgets = sorted(list(appdef["Widgets"].values()), key=attrgetter('buttonIndex'))
    for w in widgets:
        buttonArea = w.buttonAreaForTheme(theme)
        if buttonArea == WebAppWidget.BUTTON_AREA_LEFT:
            top = left
            left += w.buttonHeight + margin
        elif buttonArea == WebAppWidget.BUTTON_AREA_RIGHT:
            top = right
            right += w.buttonHeight + margin
        else:
            continue
        css = css.replace(w.cssName + " {", w.cssName + "{\n\ttop:%ipx;" % top)
    qcolor = iface.mapCanvas().canvasColor()
    color = "rgb(%i, %i, %i)" % (qcolor.red(), qcolor.green(), qcolor.blue())
    css = css.replace("canvas {", "canvas {\nbackground-color: %s" % color)
    with open(dst, "w") as f:
        f.write(css)

def writeHtml(appdef, folder, app, progress, filename):
    layers = appdef["Layers"]
    viewCrs = appdef["Settings"]["App view CRS"]
    useViewCrs = appdef["Settings"]["Use view CRS for WFS connections"]

    for applayer in layers:
        layer = applayer.layer
        if layer.providerType().lower() == "wfs":
            epsg = layer.crs().authid().split(":")[-1]
            if not useViewCrs and epsg not in ["3857", "4326"]:
                app.scripts.append('<script src="./resources/js/proj4.js"></script>')
                app.scripts.append('<script src="http://epsg.io/%s.js"></script>' % epsg)

    app.scripts.append('<script src="./resources/js/wabhelper.js"></script>')
    app.scripts.append('<script src="./resources/js/turf.min.js"></script>')
    app.scripts.append('<script src="https://cdn.rawgit.com/bjornharrtell/jsts/gh-pages/1.4.0/jsts.min.js"></script>')
    app.scripts.append('<script src="./resources/js/qgis2web_expressions.js"></script>')


    viewEpsg = viewCrs.split(":")[-1]
    if viewEpsg not in ["3857", "4326"]:
        app.scripts.append('<script src="./resources/js/proj4.js"></script>')
        app.scripts.append('<script src="http://epsg.io/%s.js"></script>' % viewEpsg)

    values = {"@VERSION@": plugins_metadata_parser["webappbuilder"].get("general","version"),
              "@SDKVERSION@": utils.sdkVersion(),
              "@TITLE@": appdef["Settings"]["Title"],
              "@SCRIPTS@": "\n".join(list(OrderedDict((item,None) for item in app.scripts).keys())),
              "@SCRIPTSBODY@": "\n".join(list(OrderedDict((item,None) for item in app.scriptsbody).keys()))
             }

    template = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    html = replaceInTemplate(template, values)

    indexFilepath = os.path.join(folder, filename)
    with codecs.open(indexFilepath, "w", encoding="utf-8") as f:
        f.write(html)

def writeLayersAndGroups(appdef, folder, app, progress):
    base = appdef["Base layers"]
    layers = appdef["Layers"]
    groups = appdef["Groups"]
    widgets = appdef["Widgets"]
    baseJs =[]
    overlaysJs =[]
    for b in base:
        if b in baseLayers:
            baseJs.append(baseLayers[b])
        elif b in baseOverlays:
            overlaysJs.append(baseOverlays[b])

    baseLayer = '''var baseLayers = [%s];''' % ",".join(baseJs)

    baseLayer += '''var baseLayersGroup = new ol.layer.Group({showContent: true,
                    'isGroupExpanded': false, 'type': 'base-group',
                    'title': 'Base maps', layers: baseLayers});'''

    if overlaysJs:
        overlayLayer = '''var overlayLayers = [%s];''' % ",".join(overlaysJs)
    else:
        overlayLayer = "var overlayLayers = [];"

    overlayLayer += '''var overlaysGroup = new ol.layer.Group({showContent: true,
                        'isGroupExpanded': false, 'title': 'Overlays', layers: overlayLayers});'''

    if "overviewmap" in widgets:
        overviewMapBaseLayerName = widgets["overviewmap"].parameters()["Base layer"]
        if overviewMapBaseLayerName == "Use main map base layer":
            baseLayer += "var overviewMapBaseLayer = baseLayersGroup;"
        else:
            baseLayer += "var overviewMapBaseLayer = %s;" % baseLayers[overviewMapBaseLayerName]

    layerVars = []
    progress.setText("Writing layer definitions")
    for i, layer in enumerate(layers):
        layerTitle = layer.layer.name() if layer.showInControls else None
        showInOverview = "overviewmap" in widgets and layer.showInOverview
        layerVars.append(layerToJavascript(layer, appdef["Settings"], layerTitle, showInOverview))
        progress.setProgress(int((i+1)*100.0/len(layers)))
    layerVars = "\n".join(layerVars)
    groupVars = ""
    groupedLayers = {}
    for group, groupDef in groups.items():
        groupLayers = groupDef["layers"]
        groupVars +=  ('''var %s = new ol.layer.Group({
                                layers: [%s],
                                showContent: %s,
                                isGroupExpanded: %s,
                                title: "%s"});\n''' %
                ("group_" + safeName(group), ",".join(["lyr_" + safeName(layer.name()) for layer in groupLayers]),
                str(groupDef["showContent"]).lower(), str(groupDef["isGroupExpanded"]).lower(), group))
        for layer in groupLayers:
            groupedLayers[layer.id()] = safeName(group)

    visibility = "\n".join(["lyr_%s.setVisible(%s);" % (safeName(layer.layer.name()),
                                                str(layer.visible).lower()) for layer in layers])
    if baseJs:
        visibility += "\nfor (var i=0;i<baseLayers.length;i++){baseLayers[i].setVisible(false);}\n"
        visibility += "baseLayers[0].setVisible(true);"

    layersList_ = []
    usedGroups = []
    for appLayer in layers:
        layer = appLayer.layer
        if layer.id() in groupedLayers:
            groupName = groupedLayers[layer.id()]
            if groupName not in usedGroups:
                layersList_.append("group_" + safeName(groupName))
                usedGroups.append(groupName)
        else:
            layersList_.append("lyr_" + safeName(layer.name()))



    layersList = "var layersList = [%s];" % (",".join([layer for layer in layersList_]))
    layersMap = "var layersMap  = {%s};" % (",".join(["'%s':%s" % (layer, layer) for layer in layersList_]))
    groupBaseLayers = appdef["Settings"]["Group base layers"]

    if baseJs:
        if groupBaseLayers:
            layersList += "layersList.unshift(baseLayersGroup);"
        else:
            layersList += "Array.prototype.splice.apply(layersList, [0, 0].concat(baseLayers));"

    if overlaysJs:
        if groupBaseLayers:
            layersList += "layersList.push(overlaysGroup);"
        else:
            layersList += "layersList.push.apply(layersList, overlayLayers);"

    app.variables.append(baseLayer)
    app.variables.append(overlayLayer)
    app.variables.append(layerVars)
    app.variables.append(groupVars)
    app.variables.append(visibility)
    app.variables.append(layersList)
    app.variables.append(layersMap)


def bounds(useCanvas, layers, crsid):
    extent = None
    if useCanvas:
        canvas = iface.mapCanvas()
        canvasCrs = canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(canvasCrs,
                                           QgsCoordinateReferenceSystem(crsid),
                                           QgsProject.instance())
        try:
            extent = transform.transform(canvas.extent())
        except:
            extent = None
    if extent is None:
        for layer in layers:
            transform = QgsCoordinateTransform(layer.layer.crs(),
                                               QgsCoordinateReferenceSystem(crsid),
                                               QgsProject.instance())
            try:
                layerExtent = transform.transform(layer.layer.extent())
                if extent is None:
                    extent = layerExtent
                else:
                    extent.combineExtentWith(layerExtent)
            except QgsCsException:
                pass

    if extent is None:
        extent = QgsRectangle(-180, -90, 180, 90)
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("ESPG:4326"),
                                           QgsCoordinateReferenceSystem(crsid),
                                           QgsProject.instance())
        extent = transform.transform(extent)

    return "[%f, %f, %f, %f]" % (extent.xMinimum(), extent.yMinimum(),
                                extent.xMaximum(), extent.yMaximum())
